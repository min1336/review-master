"""리포트 작업 Repository

비동기 리포트 생성 작업 상태 관리
"""

from __future__ import annotations

import logging
from datetime import datetime

from core.timezone import utc_now
from typing import Any
from uuid import UUID

from supabase._async.client import AsyncClient

from .base import BaseRepository

logger = logging.getLogger(__name__)


class ReportJobRepository(BaseRepository):
    """비동기 리포트 작업 상태 Repository"""

    TABLE = "report_jobs"
    VALID_STATUSES = {"pending", "processing", "completed", "failed"}

    @property
    def table_name(self) -> str:
        return self.TABLE

    async def create(
        self,
        branch_id: int,
        period_start: datetime,
        period_end: datetime,
    ) -> dict[str, Any] | None:
        """
        새 작업 생성

        Args:
            branch_id: 지점 ID
            period_start: 시작일
            period_end: 종료일

        Returns:
            생성된 작업 데이터 (id 포함)
        """
        try:
            data = {
                "branch_id": branch_id,
                "period_start": period_start.strftime("%Y-%m-%d"),
                "period_end": period_end.strftime("%Y-%m-%d"),
                "status": "pending",
                "progress": 0,
            }

            result = await self._client.table(self.TABLE).insert(data).execute()

            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"작업 생성 실패: {e}")
            raise

    async def get_by_id(self, job_id: str | UUID) -> dict[str, Any] | None:
        """
        작업 ID로 조회

        Args:
            job_id: 작업 UUID

        Returns:
            작업 데이터 또는 None
        """
        try:
            result = (
                await self._client.table(self.TABLE)
                .select("*")
                .eq("id", str(job_id))
                .single()
                .execute()
            )
            return result.data
        except Exception as e:
            logger.debug(f"작업 조회 실패 (없음): {e}")
            return None

    async def update_status(
        self,
        job_id: str | UUID,
        status: str,
        progress: int | None = None,
        error_message: str | None = None,
        report_id: int | None = None,
    ) -> bool:
        """
        작업 상태 업데이트

        Args:
            job_id: 작업 UUID
            status: 상태 (pending/processing/completed/failed)
            progress: 진행률 (0-100)
            error_message: 에러 메시지 (실패 시)
            report_id: 생성된 리포트 ID (완료 시)

        Returns:
            업데이트 성공 여부

        Raises:
            ValueError: 유효하지 않은 상태값
        """
        # 상태값 검증
        if status not in self.VALID_STATUSES:
            raise ValueError(
                f"유효하지 않은 상태: {status}. "
                f"허용된 값: {', '.join(self.VALID_STATUSES)}"
            )

        try:
            data: dict[str, Any] = {"status": status}

            if progress is not None:
                data["progress"] = progress
            if error_message is not None:
                data["error_message"] = error_message
            if report_id is not None:
                data["report_id"] = report_id

            await self._client.table(self.TABLE).update(data).eq(
                "id", str(job_id)
            ).execute()
            return True
        except Exception as e:
            logger.error(f"작업 상태 업데이트 실패: {e}")
            return False

    async def update_progress(self, job_id: str | UUID, progress: int) -> bool:
        """
        진행률만 업데이트

        Args:
            job_id: 작업 UUID
            progress: 진행률 (0-100)

        Returns:
            업데이트 성공 여부
        """
        return await self.update_status(job_id, "processing", progress=progress)

    async def get_pending_jobs(self, limit: int = 10) -> list[dict[str, Any]]:
        """
        대기 중인 작업 목록 조회

        Args:
            limit: 조회 개수

        Returns:
            대기 중인 작업 목록
        """
        try:
            result = (
                await self._client.table(self.TABLE)
                .select("*")
                .eq("status", "pending")
                .order("created_at", desc=False)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"대기 작업 조회 실패: {e}")
            return []

    async def get_by_branch_and_period(
        self,
        branch_id: int,
        period_start: datetime,
        period_end: datetime,
        status: str | None = None,
    ) -> dict[str, Any] | None:
        """
        동일 조건의 기존 작업 조회

        Args:
            branch_id: 지점 ID
            period_start: 시작일
            period_end: 종료일
            status: 상태 필터 (선택)

        Returns:
            작업 데이터 또는 None
        """
        try:
            query = (
                self._client.table(self.TABLE)
                .select("*")
                .eq("branch_id", branch_id)
                .eq("period_start", period_start.strftime("%Y-%m-%d"))
                .eq("period_end", period_end.strftime("%Y-%m-%d"))
            )

            if status:
                query = query.eq("status", status)

            result = await query.order("created_at", desc=True).limit(1).execute()

            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.debug(f"작업 조회 실패: {e}")
            return None

    async def get_active_by_branch_and_period(
        self,
        branch_id: int,
        period_start: datetime,
        period_end: datetime,
    ) -> dict[str, Any] | None:
        """
        동일 조건의 활성 작업 조회 (pending 또는 processing)

        Race condition 방지를 위해 pending과 processing 상태 모두 확인합니다.

        Args:
            branch_id: 지점 ID
            period_start: 시작일
            period_end: 종료일

        Returns:
            활성 작업 데이터 또는 None
        """
        try:
            result = (
                await self._client.table(self.TABLE)
                .select("*")
                .eq("branch_id", branch_id)
                .eq("period_start", period_start.strftime("%Y-%m-%d"))
                .eq("period_end", period_end.strftime("%Y-%m-%d"))
                .in_("status", ["pending", "processing"])
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )

            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.debug(f"활성 작업 조회 실패: {e}")
            return None

    async def cleanup_old_jobs(self, days: int = 7) -> int:
        """
        오래된 작업 정리

        Args:
            days: 보관 기간 (일)

        Returns:
            삭제된 작업 수
        """
        try:
            from datetime import timedelta

            cutoff = (utc_now() - timedelta(days=days)).isoformat()

            result = (
                await self._client.table(self.TABLE)
                .delete()
                .lt("created_at", cutoff)
                .in_("status", ["completed", "failed"])
                .execute()
            )

            return len(result.data) if result.data else 0
        except Exception as e:
            logger.error(f"오래된 작업 정리 실패: {e}")
            return 0

    async def mark_stale_jobs_failed(
        self,
        stale_minutes: int = 30,
        error_message: str = "작업 시간 초과",
    ) -> int:
        """
        고아 작업을 실패로 마킹 (서버 재시작 복구용)

        processing 상태로 지정된 시간 이상 방치된 작업들을 failed로 변경합니다.

        Args:
            stale_minutes: 고아 작업으로 판단할 시간 (분)
            error_message: 실패 메시지

        Returns:
            복구된 작업 수
        """
        try:
            from datetime import timedelta

            cutoff = (utc_now() - timedelta(minutes=stale_minutes)).isoformat()

            result = (
                await self._client.table(self.TABLE)
                .update({"status": "failed", "error_message": error_message})
                .eq("status", "processing")
                .lt("updated_at", cutoff)
                .execute()
            )

            count = len(result.data) if result.data else 0
            if count > 0:
                logger.info(f"고아 작업 {count}개를 failed로 마킹")
            return count
        except Exception as e:
            logger.error(f"고아 작업 복구 실패: {e}")
            return 0
