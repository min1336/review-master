"""Step 2: branch_reviews.sentiment 업데이트"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import update

from repository.orm_models import BranchReviewORM
from schemas.dto import ProcessedReviewDTO

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ReviewSentimentUpdater:
    """branch_reviews.sentiment 업데이트"""

    async def update(
        self, session: AsyncSession, processed: list[ProcessedReviewDTO]
    ) -> int:
        """리뷰의 sentiment 컬럼을 업데이트한다."""
        # Group review IDs by sentiment value
        sentiment_groups: dict[str, list[int]] = {}
        skipped = 0
        for pr in processed:
            if not pr.review.id or pr.review.id == 0:
                skipped += 1
                continue
            if pr.sentiment not in sentiment_groups:
                sentiment_groups[pr.sentiment] = []
            sentiment_groups[pr.sentiment].append(pr.review.id)

        if skipped:
            logger.warning(
                "review_id 누락으로 sentiment 업데이트 건너뜀: %s/%s건",
                skipped, len(processed),
            )

        updated = 0
        failed = 0

        # Batch update by sentiment value
        for sentiment, review_ids in sentiment_groups.items():
            try:
                await session.execute(
                    update(BranchReviewORM)
                    .where(BranchReviewORM.review_id.in_(review_ids))
                    .values(sentiment=sentiment)
                )
                updated += len(review_ids)
            except Exception as e:
                logger.warning(
                    f"sentiment 업데이트 실패 (sentiment={sentiment}, count={len(review_ids)}): {e}"
                )
                failed += len(review_ids)
                continue

        logger.info(
            f"sentiment 업데이트: 성공 {updated}, 실패 {failed}/{updated + failed}"
        )
        return updated
