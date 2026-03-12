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


async def _load_tags(session) -> dict[str, int]:
    from sqlalchemy import select
    from repository.orm_models import TagORM

    result = await session.execute(
        select(TagORM.id, TagORM.name).where(TagORM.is_active.is_(True))
    )
    tag_name_to_id: dict[str, int] = {row.name: row.id for row in result.all()}
    logger.info("Tags loaded: %d", len(tag_name_to_id))
    return tag_name_to_id


async def _init_classifier():
    from domain.analysis import HybridClassifier
    from domain.analysis._singletons import get_kiwi

    logger.info("Initializing HybridClassifier...")
    classifier = HybridClassifier()
    kiwi = get_kiwi()
    logger.info("Classifier ready")
    return classifier, kiwi


async def _get_total_reviews(session) -> int:
    from sqlalchemy import func, select
    from repository.orm_models import BranchReviewORM

    total_result = await session.execute(
        select(func.count()).select_from(BranchReviewORM)
    )
    total_reviews = total_result.scalar_one()
    logger.info("Total reviews to retag: %d", total_reviews)
    return total_reviews


def _extract_keywords(kiwi, content: str) -> list[str]:
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
    return keywords


def _build_upsert_rows(
    rows,
    classifier,
    kiwi,
    tag_name_to_id: dict[str, int],
) -> list[dict]:
    upsert_rows: list[dict] = []
    for row in rows:
        content = row.content
        if not content or len(content.strip()) < 5:
            continue

        keywords = _extract_keywords(kiwi, content)
        tag_sentiments = classifier.classify_review(review=content, keywords=keywords)

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
    return upsert_rows


async def _retag_in_batches(
    session,
    classifier,
    kiwi,
    tag_name_to_id: dict[str, int],
    total_reviews: int,
) -> tuple[int, int]:
    from sqlalchemy import delete, func, select
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from repository.orm_models import BranchReviewORM, ReviewTagMappingORM

    offset = 0
    total_mappings = 0
    total_deleted = 0
    start_time = time.time()

    while offset < total_reviews:
        batch_start = time.time()

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

        del_result = await session.execute(
            delete(ReviewTagMappingORM).where(
                ReviewTagMappingORM.review_id.in_(review_ids)
            )
        )
        total_deleted += del_result.rowcount

        upsert_rows = _build_upsert_rows(rows, classifier, kiwi, tag_name_to_id)

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
    return total_deleted, total_mappings


async def _assign_fallback_tag(session, tag_name_to_id: dict[str, int]) -> None:
    from sqlalchemy import text

    general_tag_id = tag_name_to_id.get("일반")
    if not general_tag_id:
        logger.warning("'일반' tag not found — skipping fallback")
        return

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


async def _reaggregate_branch_tags(session) -> None:
    from sqlalchemy import text

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


async def main():
    from core.config import get_settings
    from repository.database import get_session_factory, init_db

    settings = get_settings()
    init_db(settings.get_database_url())
    factory = get_session_factory()

    session = factory()
    try:
        tag_name_to_id = await _load_tags(session)
        classifier, kiwi = await _init_classifier()
        total_reviews = await _get_total_reviews(session)
        await _retag_in_batches(session, classifier, kiwi, tag_name_to_id, total_reviews)
        await _assign_fallback_tag(session, tag_name_to_id)
        await _reaggregate_branch_tags(session)
    except Exception as e:
        logger.error("Fatal error: %s", e, exc_info=True)
        await session.rollback()
        raise
    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
