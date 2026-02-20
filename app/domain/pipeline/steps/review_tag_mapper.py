"""Step 7: review_tag_mappings 저장 (리뷰별 태그+감정 매핑)"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from schemas.dto import ProcessedReviewDTO

if TYPE_CHECKING:
    from supabase import AsyncClient

logger = logging.getLogger(__name__)


class ReviewTagMapper:
    """review_tag_mappings 테이블에 (review_id, tag_id, sentiment) 매핑 저장"""

    async def save(
        self, client: AsyncClient, processed: list[ProcessedReviewDTO]
    ) -> int:
        """tag_sentiments에서 (review_id, tag_id, sentiment) 조합 추출 후 upsert"""
        # 1. 전체 tag_name → tag_id 일괄 조회
        all_tag_names: set[str] = set()
        for pr in processed:
            for tag_name in pr.tag_sentiments:
                if tag_name != "기타":
                    all_tag_names.add(tag_name)

        if not all_tag_names:
            return 0

        tag_id_cache: dict[str, int] = {}
        try:
            result = await (
                client.table("tags")
                .select("id, name")
                .in_("name", list(all_tag_names))
                .execute()
            )
            for row in result.data:
                tag_id_cache[row["name"]] = row["id"]
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

        # 3. 배치 upsert (500건 단위)
        saved = 0
        batch_size = 500
        for i in range(0, len(upsert_rows), batch_size):
            batch = upsert_rows[i : i + batch_size]
            try:
                await (
                    client.table("review_tag_mappings")
                    .upsert(batch, on_conflict="review_id,tag_id,sentiment")
                    .execute()
                )
                saved += len(batch)
            except Exception as e:
                logger.warning(f"review_tag_mappings upsert 실패 (batch {i}): {e}")

        logger.info(f"review_tag_mappings 저장 완료: {saved}건")
        return saved
