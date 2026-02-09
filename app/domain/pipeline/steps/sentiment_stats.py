"""Step 3: branch_sentiment_stats 증분 업데이트"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from schemas.dto import ProcessedReviewDTO

if TYPE_CHECKING:
    from supabase import AsyncClient

logger = logging.getLogger(__name__)


class SentimentStatsUpdater:
    """branch_sentiment_stats 증분 업데이트 (지점별 배치)"""

    async def update(
        self, client: AsyncClient, processed: list[ProcessedReviewDTO]
    ) -> int:
        """지점별로 메모리 집계 후 1회 DB 업데이트"""
        # 1. 지점별 감정 카운트 집계
        branch_counts: dict[int, dict[str, int]] = {}
        for pr in processed:
            bid = pr.branch_id
            if bid not in branch_counts:
                branch_counts[bid] = {"positive": 0, "negative": 0, "neutral": 0}
            branch_counts[bid][pr.sentiment] += 1

        # 2. 지점별 1회 DB 업데이트
        # NOTE: SELECT→증분→UPSERT 패턴은 동시 실행 시 카운트 누락 가능 (race condition).
        # 완전한 해결: PostgreSQL RPC 함수로 atomic increment 구현 필요.
        # 현재는 단일 프로세스 실행 환경이므로 실질적 문제 없음.
        updated = 0
        for branch_id, counts in branch_counts.items():
            try:
                result = await (
                    client.table("branch_sentiment_stats")
                    .select("*")
                    .eq("branch_id", branch_id)
                    .execute()
                )

                if result.data:
                    row = result.data[0]
                    new_pos = (row.get("positive_count", 0) or 0) + counts["positive"]
                    new_neg = (row.get("negative_count", 0) or 0) + counts["negative"]
                    new_neu = (row.get("neutral_count", 0) or 0) + counts["neutral"]
                else:
                    new_pos = counts["positive"]
                    new_neg = counts["negative"]
                    new_neu = counts["neutral"]

                total = new_pos + new_neg + new_neu

                await (
                    client.table("branch_sentiment_stats")
                    .upsert(
                        {
                            "branch_id": branch_id,
                            "positive_count": new_pos,
                            "negative_count": new_neg,
                            "neutral_count": new_neu,
                            "total_count": total,
                            "positive_ratio": (
                                round(new_pos / total * 100, 2) if total > 0 else 0
                            ),
                            "negative_ratio": (
                                round(new_neg / total * 100, 2) if total > 0 else 0
                            ),
                        },
                        on_conflict="branch_id",
                    )
                    .execute()
                )
                updated += 1
            except Exception as e:
                logger.warning(f"감정 통계 업데이트 실패 (branch_id={branch_id}): {e}")
                continue

        return updated
