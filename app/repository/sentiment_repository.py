"""
감정통계 Repository (branch_sentiment_stats 테이블)
"""

from __future__ import annotations

import logging

from models.sentiment import SentimentStats
from schemas.dto import SentimentStatsDTO

from .base import BaseRepository

logger = logging.getLogger(__name__)


class SentimentRepository(BaseRepository[SentimentStats]):
    """branch_sentiment_stats 테이블 Repository"""

    model = SentimentStats

    @property
    def table_name(self) -> str:
        return "branch_sentiment_stats"

    async def upsert_stats(self, stats_list: list[dict]) -> int:
        """지점별 감정통계 저장"""
        success_count = 0

        for stat in stats_list:
            try:
                total = (
                    stat["positive_count"]
                    + stat["negative_count"]
                    + stat["neutral_count"]
                )
                pos_cnt = stat["positive_count"]
                neg_cnt = stat["negative_count"]
                positive_ratio = (pos_cnt / total * 100) if total > 0 else 0
                negative_ratio = (neg_cnt / total * 100) if total > 0 else 0

                await (
                    self._client.table(self.table_name)
                    .upsert(
                        {
                            "branch_id": stat["branch_id"],
                            "positive_count": stat["positive_count"],
                            "negative_count": stat["negative_count"],
                            "neutral_count": stat["neutral_count"],
                            "total_count": total,
                            "positive_ratio": round(positive_ratio, 2),
                            "negative_ratio": round(negative_ratio, 2),
                            "updated_at": "now()",
                        },
                        on_conflict="branch_id",
                    )
                    .execute()
                )
                success_count += 1
            except Exception as e:
                branch_id = stat.get("branch_id")
                logger.warning(
                    f"Failed to upsert sentiment stats for branch {branch_id}: {e}"
                )

        return success_count

    async def get_stats(self, branch_id: int | None = None) -> SentimentStatsDTO:
        """감정통계 조회"""
        if branch_id:
            # 특정 지점
            result = (
                await self._client.table(self.table_name)
                .select("*")
                .eq("branch_id", branch_id)
                .execute()
            )
            if result.data:
                row = result.data[0]
                return SentimentStatsDTO(
                    positive=row["positive_count"],
                    negative=row["negative_count"],
                    neutral=row["neutral_count"],
                    total=row["total_count"],
                    positive_ratio=float(row["positive_ratio"]),
                    negative_ratio=float(row["negative_ratio"]),
                )
        else:
            # 전체 합계
            result = await self._client.table(self.table_name).select("*").execute()
            if result.data:
                totals = {"positive": 0, "negative": 0, "neutral": 0, "total": 0}
                for row in result.data:
                    totals["positive"] += row["positive_count"]
                    totals["negative"] += row["negative_count"]
                    totals["neutral"] += row["neutral_count"]
                    totals["total"] += row["total_count"]

                if totals["total"] > 0:
                    positive_ratio = round(
                        totals["positive"] / totals["total"] * 100, 2
                    )
                    negative_ratio = round(
                        totals["negative"] / totals["total"] * 100, 2
                    )
                else:
                    positive_ratio = 0
                    negative_ratio = 0

                return SentimentStatsDTO(
                    positive=totals["positive"],
                    negative=totals["negative"],
                    neutral=totals["neutral"],
                    total=totals["total"],
                    positive_ratio=positive_ratio,
                    negative_ratio=negative_ratio,
                )

        return SentimentStatsDTO(
            positive=0,
            negative=0,
            neutral=0,
            total=0,
            positive_ratio=0,
            negative_ratio=0,
        )

    async def get_all_stats(self) -> list[SentimentStats]:
        """전체 지점 감정통계 목록"""
        result = (
            await self._client.table(self.table_name)
            .select("*")
            .order("branch_id")
            .execute()
        )
        return [self.model(**row) for row in result.data]
