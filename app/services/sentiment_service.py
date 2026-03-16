"""
감정통계 Service - 비즈니스 로직
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from schemas.dto import SentimentStatsDTO

if TYPE_CHECKING:
    from repository.review_repository import SentimentRepository


class SentimentService:
    """감정통계 비즈니스 로직"""

    def __init__(self, sentiment_repo: SentimentRepository):
        self.sentiment_repo = sentiment_repo

    async def get_stats(self, branch_id: int | None = None) -> SentimentStatsDTO:
        """감정통계 조회"""
        return await self.sentiment_repo.get_stats(branch_id)

    async def get_all_stats(self, page: int = 1, limit: int = 50) -> tuple[list[dict], int]:
        """전체 지점 감정통계 (페이지네이션)"""
        return await self.sentiment_repo.get_all_stats(page=page, limit=limit)
