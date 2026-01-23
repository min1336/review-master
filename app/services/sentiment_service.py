"""
감정통계 Service - 비즈니스 로직
"""
from typing import Optional, List

from crud import UnitOfWork


class SentimentService:
    """감정통계 비즈니스 로직"""

    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def get_stats(self, branch_id: Optional[int] = None) -> dict:
        """감정통계 조회"""
        return await self.uow.sentiments.get_stats(branch_id)

    async def get_all_stats(self) -> List[dict]:
        """전체 지점 감정통계"""
        return await self.uow.sentiments.get_all_stats()

    async def upsert_stats(self, stats_list: List[dict]) -> int:
        """감정통계 저장"""
        return await self.uow.sentiments.upsert_stats(stats_list)

    # ============================================================
    # 리뷰 관련
    # ============================================================

    async def search_reviews(
        self,
        sentiment: Optional[str] = None,
        branch_id: Optional[int] = None,
        limit: int = 100,
        offset: int = 0
    ) -> dict:
        """최근 리뷰 검색"""
        result = await self.uow.reviews.search(sentiment, branch_id, limit, offset)

        # 통계 추가
        stats = await self.uow.sentiments.get_stats(branch_id)
        result['stats'] = stats

        return result

    async def cleanup_reviews(self, days: int = 30, max_per_branch: int = 30) -> dict:
        """리뷰 정리"""
        return await self.uow.reviews.cleanup(days, max_per_branch)
