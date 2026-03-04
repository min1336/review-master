"""요약 승인 Mixin

SummaryService에서 분리된 승인/거절 관련 메서드.
의존성: summary_repo
"""

from __future__ import annotations

import logging

from schemas.dto import PendingSummaryResultDTO

logger = logging.getLogger(__name__)


class SummaryApprovalMixin:
    """요약 승인/거절 메서드"""

    async def get_pending_summaries(self, limit: int = 50) -> list[dict]:
        """승인 대기 중인 요약 목록 조회"""
        return await self.summary_repo.get_pending_summaries(limit)

    async def get_history(self, branch_id: int, limit: int = 10) -> list[dict]:
        """요약 변경 히스토리 조회"""
        return await self.summary_repo.get_history(branch_id, limit)

    async def approve_pending_summary(self, branch_id: int) -> dict | None:
        """대기 중인 요약 승인"""
        return await self.summary_repo.approve_pending_summary(branch_id)

    async def reject_pending_summary(self, branch_id: int) -> dict | None:
        """대기 중인 요약 거부"""
        return await self.summary_repo.reject_pending_summary(branch_id)

    async def apply_pending_summary(
        self, branch_id: int, period: str
    ) -> PendingSummaryResultDTO:
        """대기 중인 요약을 적용 (pending → main)"""
        summary = await self.summary_repo.get_by_branch_id(branch_id)
        if not summary:
            raise ValueError(f"지점 {branch_id}을(를) 찾을 수 없습니다")

        summary_data = summary.model_dump()
        pending = summary_data.get("pending_summaries") or {}

        if period not in pending:
            raise ValueError(f"대기 중인 {period} 요약이 없습니다")

        field_map = {
            "all": "summary_all",
            "1y": "summary_1y",
            "6m": "summary_6m",
            "3m": "summary_3m",
            "1m": "summary_1m",
        }

        new_summary = pending.pop(period)

        await self.summary_repo.upsert_by_branch_id(
            {
                "branch_id": branch_id,
                field_map[period]: new_summary,
                "pending_summaries": pending,
            }
        )

        return PendingSummaryResultDTO(period=period, applied=new_summary)

    async def discard_pending_summary(
        self, branch_id: int, period: str
    ) -> PendingSummaryResultDTO:
        """대기 중인 요약 취소 (삭제)"""
        summary = await self.summary_repo.get_by_branch_id(branch_id)
        if not summary:
            raise ValueError(f"지점 {branch_id}을(를) 찾을 수 없습니다")

        summary_data = summary.model_dump()
        pending = summary_data.get("pending_summaries") or {}

        if period in pending:
            del pending[period]
            await self.summary_repo.upsert_by_branch_id(
                {"branch_id": branch_id, "pending_summaries": pending}
            )

        return PendingSummaryResultDTO(period=period, discarded=period)
