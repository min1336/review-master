"""스케줄러 설정 Repository"""

from __future__ import annotations

import logging
from datetime import datetime

from core.timezone import utc_now
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from supabase import AsyncClient

logger = logging.getLogger(__name__)


class SchedulerSettingsRepository:
    """업체별 스케줄러 설정 Repository"""

    TABLE_NAME = "branch_scheduler_settings"

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def get_by_branch_id(self, branch_id: int) -> dict | None:
        """업체별 설정 조회"""
        try:
            result = await self._client.table(self.TABLE_NAME).select(
                "*"
            ).eq("branch_id", branch_id).execute()

            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"설정 조회 오류: {e}")
            return None

    async def upsert(self, data: dict) -> dict | None:
        """설정 생성/수정"""
        try:
            data["updated_at"] = utc_now().isoformat()

            result = await self._client.table(self.TABLE_NAME).upsert(
                data, on_conflict="branch_id"
            ).execute()

            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"설정 저장 오류: {e}")
            return None

    async def update_last_summary(
        self, branch_id: int, last_summary_at: datetime, next_summary_at: datetime
    ) -> bool:
        """마지막 요약 시간 업데이트"""
        try:
            await self._client.table(self.TABLE_NAME).update({
                "last_summary_at": last_summary_at.isoformat(),
                "next_summary_at": next_summary_at.isoformat(),
                "updated_at": utc_now().isoformat(),
            }).eq("branch_id", branch_id).execute()

            return True
        except Exception as e:
            logger.error(f"마지막 요약 시간 업데이트 오류: {e}")
            return False

    async def get_branches_due_for_summary(self) -> list[dict]:
        """요약 생성이 필요한 업체 목록 조회"""
        try:
            now = utc_now().isoformat()

            result = await self._client.table(self.TABLE_NAME).select(
                "*"
            ).lte("next_summary_at", now).execute()

            return result.data or []
        except Exception as e:
            logger.error(f"요약 대상 조회 오류: {e}")
            return []

    async def get_all(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """전체 설정 목록 조회"""
        try:
            result = await self._client.table(self.TABLE_NAME).select(
                "*"
            ).order("branch_id").range(offset, offset + limit - 1).execute()

            return result.data or []
        except Exception as e:
            logger.error(f"설정 목록 조회 오류: {e}")
            return []

    async def delete(self, branch_id: int) -> bool:
        """설정 삭제"""
        try:
            await self._client.table(self.TABLE_NAME).delete().eq(
                "branch_id", branch_id
            ).execute()

            return True
        except Exception as e:
            logger.error(f"설정 삭제 오류: {e}")
            return False
