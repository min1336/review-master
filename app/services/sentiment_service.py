"""
감정통계 Service - 비즈니스 로직
"""

from __future__ import annotations

from schemas.dto import SentimentStatsDTO


class SentimentService:
    """감정통계 비즈니스 로직"""

    def __init__(self, sentiment_repo):
        self.sentiment_repo = sentiment_repo

    async def get_stats(self, branch_id: int | None = None) -> SentimentStatsDTO:
        """감정통계 조회"""
        return await self.sentiment_repo.get_stats(branch_id)

    async def get_all_stats(self) -> list[dict]:
        """전체 지점 감정통계"""
        return await self.sentiment_repo.get_all_stats()
