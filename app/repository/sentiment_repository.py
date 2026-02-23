"""
감정통계 Repository (monthly_sentiment_stats 테이블 집계)
"""

from __future__ import annotations

import logging

from schemas.dto import SentimentStatsDTO

from .base import BaseRepository

logger = logging.getLogger(__name__)


class SentimentRepository(BaseRepository):
    """monthly_sentiment_stats 기반 감정통계 Repository"""

    @property
    def table_name(self) -> str:
        return "monthly_sentiment_stats"

    async def get_stats(self, branch_id: int | None = None) -> SentimentStatsDTO:
        """감정통계 조회 — monthly_sentiment_stats에서 월별 데이터 집계"""
        query = self._client.table(self.table_name).select(
            "positive_count, negative_count, neutral_count"
        )
        if branch_id:
            query = query.eq("branch_id", branch_id)

        result = await query.execute()

        if not result.data:
            return SentimentStatsDTO(
                positive=0, negative=0, neutral=0,
                total=0, positive_ratio=0, negative_ratio=0,
            )

        pos = neg = neu = 0
        for row in result.data:
            pos += row.get("positive_count", 0) or 0
            neg += row.get("negative_count", 0) or 0
            neu += row.get("neutral_count", 0) or 0

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
        result = (
            await self._client.table(self.table_name)
            .select("branch_id, positive_count, negative_count, neutral_count")
            .execute()
        )

        if not result.data:
            return []

        branch_map: dict[int, dict[str, int]] = {}
        for row in result.data:
            bid = row["branch_id"]
            if bid not in branch_map:
                branch_map[bid] = {"positive": 0, "negative": 0, "neutral": 0}
            branch_map[bid]["positive"] += row.get("positive_count", 0) or 0
            branch_map[bid]["negative"] += row.get("negative_count", 0) or 0
            branch_map[bid]["neutral"] += row.get("neutral_count", 0) or 0

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
