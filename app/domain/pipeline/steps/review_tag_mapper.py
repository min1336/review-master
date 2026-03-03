"""Step 7: review_tag_mappings 저장 (리뷰별 태그+감정 매핑)"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from repository.orm_models import ReviewTagMappingORM, TagORM
from schemas.dto import ProcessedReviewDTO

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ReviewTagMapper:
    """review_tag_mappings 테이블에 (review_id, tag_id, sentiment) 매핑 저장"""

    async def save(
        self, session: AsyncSession, processed: list[ProcessedReviewDTO]
    ) -> int:
        """tag_sentiments에서 (review_id, tag_id, sentiment) 조합 추출 후 upsert"""
        # 1. 전체 tag_name -> tag_id 일괄 조회
        all_tag_names: set[str] = set()
        for pr in processed:
            for tag_name in pr.tag_sentiments:
                if tag_name != "기타":
                    all_tag_names.add(tag_name)

        if not all_tag_names:
            return 0

        tag_id_cache: dict[str, int] = {}
        try:
            result = await session.execute(
                select(TagORM.id, TagORM.name)
                .where(TagORM.name.in_(list(all_tag_names)))
            )
            for row in result.all():
                tag_id_cache[row.name] = row.id
        except Exception as e:
            logger.warning(f"tags 배치 조회 실패: {e}")
            return 0

        # 2. 매핑 행 생성
        upsert_rows: list[dict] = []
        for pr in processed:
            review_id = pr.review.id
            if not review_id:
                continue

            for tag_name, sentiments in pr.tag_sentiments.items():
                if tag_name == "기타":
                    continue
                tag_id = tag_id_cache.get(tag_name)
                if not tag_id:
                    continue

                for sentiment_label in ("positive", "negative", "neutral"):
                    keywords = sentiments.get(sentiment_label, [])
                    if not keywords:
                        continue

                    upsert_rows.append({
                        "review_id": review_id,
                        "tag_id": tag_id,
                        "sentiment": sentiment_label,
                        "matched_keyword": ", ".join(keywords),
                        "source": "pipeline",
                    })

        if not upsert_rows:
            return 0

        # 3. 진정한 배치 upsert (500건 단위 — 1 SQL per batch)
        tbl = ReviewTagMappingORM.__table__
        saved = 0
        batch_size = 500
        for i in range(0, len(upsert_rows), batch_size):
            batch = upsert_rows[i : i + batch_size]
            try:
                stmt = pg_insert(tbl).values(batch)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["review_id", "tag_id", "sentiment"],
                    set_={
                        "matched_keyword": stmt.excluded.matched_keyword,
                        "source": stmt.excluded.source,
                    },
                )
                await session.execute(stmt)
                saved += len(batch)
            except Exception as e:
                logger.warning(f"review_tag_mappings upsert 실패 (batch {i}): {e}")

        logger.info(f"review_tag_mappings 저장 완료: {saved}건")
        return saved
