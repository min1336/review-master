"""
감정통계 Repository (monthly_sentiment_stats 테이블 집계)
"""

from __future__ import annotations

import logging

from sqlalchemy import select
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
            MonthlySentimentStatsORM.positive_count,
            MonthlySentimentStatsORM.negative_count,
            MonthlySentimentStatsORM.neutral_count,
        )
        if branch_id:
            stmt = stmt.where(MonthlySentimentStatsORM.branch_id == branch_id)

        result = await self._session.execute(stmt)
        rows = result.all()

        if not rows:
            return SentimentStatsDTO(
                positive=0, negative=0, neutral=0,
                total=0, positive_ratio=0, negative_ratio=0,
            )

        pos = neg = neu = 0
        for row in rows:
            pos += row.positive_count or 0
            neg += row.negative_count or 0
            neu += row.neutral_count or 0

        total = pos + neg + neu
        return SentimentStatsDTO(
            positive=pos,
            negative=neg,
            neutral=neu,
            total=total,
            positive_ratio=round(pos / total * 100, 2) if total > 0 else 0,
            negative_ratio=round(neg / total * 100, 2) if total > 0 else 0,
        )

    async def get_all_stats(self) -> list[dict]:
        """전체 지점 감정통계 목록 — monthly_sentiment_stats에서 지점별 집계"""
        stmt = select(
            MonthlySentimentStatsORM.branch_id,
            MonthlySentimentStatsORM.positive_count,
            MonthlySentimentStatsORM.negative_count,
            MonthlySentimentStatsORM.neutral_count,
        )

        result = await self._session.execute(stmt)
        rows = result.all()

        if not rows:
            return []

        branch_map: dict[int, dict[str, int]] = {}
        for row in rows:
            bid = row.branch_id
            if bid not in branch_map:
                branch_map[bid] = {"positive": 0, "negative": 0, "neutral": 0}
            branch_map[bid]["positive"] += row.positive_count or 0
            branch_map[bid]["negative"] += row.negative_count or 0
            branch_map[bid]["neutral"] += row.neutral_count or 0

        stats_list = []
        for bid in sorted(branch_map):
            c = branch_map[bid]
            total = c["positive"] + c["negative"] + c["neutral"]
            stats_list.append({
                "branch_id": bid,
                "positive_count": c["positive"],
                "negative_count": c["negative"],
                "neutral_count": c["neutral"],
                "total_count": total,
                "positive_ratio": round(c["positive"] / total * 100, 2) if total > 0 else 0,
                "negative_ratio": round(c["negative"] / total * 100, 2) if total > 0 else 0,
            })

        return stats_list
