"""
감정통계 Repository (monthly_sentiment_stats 테이블 집계)
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.dto import SentimentStatsDTO

from .orm_models import MonthlySentimentStatsORM

logger = logging.getLogger(__name__)


class SentimentRepository:
    """monthly_sentiment_stats 기반 감정통계 Repository"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_stats(self, branch_id: int | None = None) -> SentimentStatsDTO:
        """감정통계 조회 — monthly_sentiment_stats에서 월별 데이터 집계"""
        stmt = select(
            func.coalesce(func.sum(MonthlySentimentStatsORM.positive_count), 0).label("pos"),
            func.coalesce(func.sum(MonthlySentimentStatsORM.negative_count), 0).label("neg"),
            func.coalesce(func.sum(MonthlySentimentStatsORM.neutral_count), 0).label("neu"),
        )
        if branch_id:
            stmt = stmt.where(MonthlySentimentStatsORM.branch_id == branch_id)

        result = await self._session.execute(stmt)
        row = result.one()

        pos, neg, neu = int(row.pos), int(row.neg), int(row.neu)
        total = pos + neg + neu
        return SentimentStatsDTO(
            positive=pos,
            negative=neg,
            neutral=neu,
            total=total,
            positive_ratio=round(pos / total * 100, 2) if total > 0 else 0,
            negative_ratio=round(neg / total * 100, 2) if total > 0 else 0,
        )

    async def get_all_stats(self, page: int = 1, limit: int = 50) -> tuple[list[dict], int]:
        """전체 지점 감정통계 목록 — monthly_sentiment_stats에서 지점별 집계 (DB 페이지네이션)"""
        # count 쿼리
        count_stmt = select(func.count(func.distinct(MonthlySentimentStatsORM.branch_id)))
        total_count = (await self._session.execute(count_stmt)).scalar() or 0

        # 데이터 쿼리 (LIMIT/OFFSET)
        offset = (page - 1) * limit
        stmt = (
            select(
                MonthlySentimentStatsORM.branch_id,
                func.coalesce(func.sum(MonthlySentimentStatsORM.positive_count), 0).label("pos"),
                func.coalesce(func.sum(MonthlySentimentStatsORM.negative_count), 0).label("neg"),
                func.coalesce(func.sum(MonthlySentimentStatsORM.neutral_count), 0).label("neu"),
            )
            .group_by(MonthlySentimentStatsORM.branch_id)
            .order_by(MonthlySentimentStatsORM.branch_id)
            .offset(offset)
            .limit(limit)
        )

        result = await self._session.execute(stmt)
        rows = result.all()

        stats_list = []
        for row in rows:
            pos, neg, neu = int(row.pos), int(row.neg), int(row.neu)
            total = pos + neg + neu
            stats_list.append({
                "branch_id": row.branch_id,
                "positive_count": pos,
                "negative_count": neg,
                "neutral_count": neu,
                "total_count": total,
                "positive_ratio": round(pos / total * 100, 2) if total > 0 else 0,
                "negative_ratio": round(neg / total * 100, 2) if total > 0 else 0,
            })

        return stats_list, total_count
