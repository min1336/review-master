"""
감정통계 Service - 비즈니스 로직
"""

from __future__ import annotations

from schemas.dto import (
    CleanupResultDTO,
    ReviewSearchResultDTO,
    SentimentStatsDTO,
)


class SentimentService:
    """감정통계 비즈니스 로직"""

    def __init__(self, sentiment_repo, review_repo):
        self.sentiment_repo = sentiment_repo
        self.review_repo = review_repo

    async def get_stats(self, branch_id: int | None = None) -> SentimentStatsDTO:
        """감정통계 조회"""
        return await self.sentiment_repo.get_stats(branch_id)

    async def get_all_stats(self) -> list[dict]:
        """전체 지점 감정통계"""
        stats_list = await self.sentiment_repo.get_all_stats()
        return [s.model_dump() for s in stats_list]

    async def upsert_stats(self, stats_list: list[dict]) -> int:
        """감정통계 저장"""
        return await self.sentiment_repo.upsert_stats(stats_list)

    # ============================================================
    # 리뷰 관련
    # ============================================================

    async def search_reviews(
        self,
        sentiment: str | None = None,
        branch_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> ReviewSearchResultDTO:
        """최근 리뷰 검색"""
        result = await self.review_repo.search(sentiment, branch_id, limit, offset)

        # 통계 추가
        stats = await self.sentiment_repo.get_stats(branch_id)

        return ReviewSearchResultDTO(
            reviews=result.reviews,
            total=result.total,
            stats=stats,
        )

    async def cleanup_reviews(
        self, days: int = 30, max_per_branch: int = 30
    ) -> CleanupResultDTO:
        """리뷰 정리"""
        return await self.review_repo.cleanup(days, max_per_branch)
