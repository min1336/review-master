"""리뷰 재태깅 스크립트

개선된 HybridClassifier 로직으로 review_tag_mappings를 재생성합니다.
- 사고 처리 오분류 수정
- 동일 카테고리 중복 태깅 방지
- 반전 구문 인식 강화

실행: cd app && ../.venv/bin/python scripts/retag_reviews.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

BATCH_SIZE = 1000
UPSERT_BATCH = 500


async def main():
    from sqlalchemy import delete, func, select, text
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from core.config import get_settings
    from domain.analysis import HybridClassifier
    from domain.analysis._singletons import get_kiwi
    from repository.database import get_session_factory, init_db
    from repository.orm_models import (
        BranchReviewORM,
        ReviewTagMappingORM,
        TagORM,
    )

    settings = get_settings()
    init_db(settings.get_database_url())
    factory = get_session_factory()

    session = factory()
    try:
        # 1. 태그 이름→ID 매핑 로드
        result = await session.execute(
            select(TagORM.id, TagORM.name).where(TagORM.is_active.is_(True))
        )
        tag_name_to_id: dict[str, int] = {row.name: row.id for row in result.all()}
        logger.info("Tags loaded: %d", len(tag_name_to_id))

        # 2. HybridClassifier + Kiwi 초기화
        logger.info("Initializing HybridClassifier...")
        classifier = HybridClassifier()
        kiwi = get_kiwi()
        logger.info("Classifier ready")

        # 3. 전체 리뷰 수 확인
        total_result = await session.execute(
            select(func.count()).select_from(BranchReviewORM)
        )
        total_reviews = total_result.scalar_one()
        logger.info("Total reviews to retag: %d", total_reviews)

        # 4. 배치 처리
        offset = 0
        total_mappings = 0
        total_deleted = 0
        start_time = time.time()

        while offset < total_reviews:
            batch_start = time.time()

            # 리뷰 배치 조회
            result = await session.execute(
                select(
                    BranchReviewORM.review_id,
                    BranchReviewORM.content,
                )
                .where(BranchReviewORM.content.isnot(None))
                .where(BranchReviewORM.deleted_at.is_(None))
                .where(func.length(BranchReviewORM.content) >= 5)
                .order_by(BranchReviewORM.review_id)
                .offset(offset)
                .limit(BATCH_SIZE)
            )
            rows = result.all()
            if not rows:
                break

            review_ids = [r.review_id for r in rows]

            # 기존 매핑 삭제
            del_result = await session.execute(
                delete(ReviewTagMappingORM).where(
                    ReviewTagMappingORM.review_id.in_(review_ids)
                )
            )
            total_deleted += del_result.rowcount

            # 새 태깅 수행
            upsert_rows: list[dict] = []
            for row in rows:
                content = row.content
                if not content or len(content.strip()) < 5:
                    continue

                # 키워드 추출 (Kiwi)
                keywords = []
                if kiwi:
                    try:
                        tokens = kiwi.tokenize(content)
                        for token in tokens:
                            if token.tag in ("NNG", "NNP", "VA", "VV", "XR"):
                                if len(token.form) >= 2:
                                    keywords.append(token.form)
                    except Exception:
                        pass

                # HybridClassifier 분류
                tag_sentiments = classifier.classify_review(
                    review=content, keywords=keywords
                )

                for tag_name, sentiments in tag_sentiments.items():
                    if tag_name == "기타":
                        continue
                    tag_id = tag_name_to_id.get(tag_name)
                    if not tag_id:
                        continue

                    for sentiment_label in ("positive", "negative", "neutral"):
                        kws = sentiments.get(sentiment_label, [])
                        if not kws:
                            continue
                        upsert_rows.append({
                            "review_id": row.review_id,
                            "tag_id": tag_id,
                            "sentiment": sentiment_label,
                            "matched_keyword": ", ".join(kws[:10]),
                            "source": "retag_v2",
                        })

            # 배치 upsert
            if upsert_rows:
                tbl = ReviewTagMappingORM.__table__
                for i in range(0, len(upsert_rows), UPSERT_BATCH):
                    batch = upsert_rows[i : i + UPSERT_BATCH]
                    stmt = pg_insert(tbl).values(batch)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["review_id", "tag_id", "sentiment"],
                        set_={
                            "matched_keyword": stmt.excluded.matched_keyword,
                            "source": stmt.excluded.source,
                        },
                    )
                    await session.execute(stmt)

            total_mappings += len(upsert_rows)
            await session.commit()

            elapsed = time.time() - batch_start
            progress = min(offset + len(rows), total_reviews)
            logger.info(
                "Batch %d-%d / %d  |  mappings: +%d  |  %.1fs  |  total: %d",
                offset, progress, total_reviews,
                len(upsert_rows), elapsed, total_mappings,
            )

            offset += BATCH_SIZE

        total_elapsed = time.time() - start_time
        logger.info(
            "=== DONE === deleted: %d, new mappings: %d, time: %.1fs",
            total_deleted, total_mappings, total_elapsed,
        )

        # 5. "일반" fallback 태깅 — 매핑 없는 리뷰에 기본 태그 부여
        general_tag_id = tag_name_to_id.get("일반")
        if general_tag_id:
            logger.info("Assigning '일반' fallback tag to unmapped reviews...")
            unmapped_result = await session.execute(text("""
                INSERT INTO review_tag_mappings (review_id, tag_id, sentiment, matched_keyword, source)
                SELECT
                    br.review_id,
                    :tag_id,
                    CASE
                        WHEN COALESCE(br.rating_service, 0) + COALESCE(br.rating_car, 0) + COALESCE(br.rating_convenience, 0) >= 12 THEN 'positive'
                        WHEN COALESCE(br.rating_service, 0) + COALESCE(br.rating_car, 0) + COALESCE(br.rating_convenience, 0) < 9 THEN 'negative'
                        ELSE 'neutral'
                    END,
                    '기본 분류',
                    'retag_v2_fallback'
                FROM branch_reviews br
                WHERE br.deleted_at IS NULL
                  AND br.content IS NOT NULL
                  AND LENGTH(br.content) >= 5
                  AND NOT EXISTS (
                      SELECT 1 FROM review_tag_mappings rtm
                      WHERE rtm.review_id = br.review_id
                  )
                ON CONFLICT (review_id, tag_id, sentiment) DO NOTHING
            """), {"tag_id": general_tag_id})
            fallback_count = unmapped_result.rowcount
            await session.commit()
            logger.info("Fallback '일반' tags assigned: %d reviews", fallback_count)
        else:
            logger.warning("'일반' tag not found — skipping fallback")

        # 6. branch_tags 재집계
        logger.info("Re-aggregating branch_tags(all)...")
        await session.execute(text("DELETE FROM branch_tags WHERE period_type = 'all'"))
        await session.execute(text("""
            INSERT INTO branch_tags (branch_id, tag_id, period_type, count, positive_count, negative_count, neutral_count, updated_at)
            SELECT
                br.branch_id, rtm.tag_id, 'all',
                COUNT(*),
                SUM(CASE WHEN rtm.sentiment = 'positive' THEN 1 ELSE 0 END),
                SUM(CASE WHEN rtm.sentiment = 'negative' THEN 1 ELSE 0 END),
                SUM(CASE WHEN rtm.sentiment = 'neutral' THEN 1 ELSE 0 END),
                NOW()
            FROM review_tag_mappings rtm
            JOIN branch_reviews br ON br.review_id = rtm.review_id
            WHERE br.deleted_at IS NULL
            GROUP BY br.branch_id, rtm.tag_id
            ON CONFLICT (branch_id, tag_id, period_type)
            DO UPDATE SET
                count = EXCLUDED.count,
                positive_count = EXCLUDED.positive_count,
                negative_count = EXCLUDED.negative_count,
                neutral_count = EXCLUDED.neutral_count,
                updated_at = NOW()
        """))
        await session.commit()
        logger.info("branch_tags re-aggregation complete")

    except Exception as e:
        logger.error("Fatal error: %s", e, exc_info=True)
        await session.rollback()
        raise
    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
