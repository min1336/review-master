"""리포트 작업 Repository

비동기 리포트 생성 작업 상태 관리
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update

from core.timezone import utc_now

from sqlalchemy.ext.asyncio import AsyncSession

from .orm_models import ReportJobORM

logger = logging.getLogger(__name__)


class ReportJobRepository:
    """비동기 리포트 작업 상태 Repository"""

    VALID_STATUSES = {"pending", "processing", "completed", "failed"}

    def __init__(self, session: AsyncSession):
        self._session = session

    @staticmethod
    def _to_dict(row: ReportJobORM) -> dict[str, Any]:
        return {c.key: getattr(row, c.key) for c in row.__table__.columns}

    async def create(
        self,
        branch_id: int,
        period_start: datetime,
        period_end: datetime,
    ) -> dict[str, Any] | None:
        """새 작업 생성"""
        try:
            data = {
                "branch_id": branch_id,
                "period_start": period_start.date(),
                "period_end": period_end.date(),
                "status": "pending",
                "progress": 0,
            }

            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = (
                pg_insert(ReportJobORM.__table__)
                .values(**data)
                .returning(ReportJobORM.__table__)
            )
            result = await self._session.execute(stmt)
            row = result.mappings().one_or_none()
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error("작업 생성 실패: %s", e)
            raise

    async def get_by_id(self, job_id: str | UUID) -> dict[str, Any] | None:
        """작업 ID로 조회"""
        try:
            stmt = (
                select(ReportJobORM)
                .where(ReportJobORM.id == str(job_id))
            )
            result = await self._session.execute(stmt)
            row = result.scalar_one_or_none()
            if row:
                return self._to_dict(row)
            return None
        except Exception as e:
            logger.debug("작업 조회 실패 (없음): %s", e)
            return None

    async def update_status(
        self,
        job_id: str | UUID,
        status: str,
        progress: int | None = None,
        error_message: str | None = None,
        report_id: int | None = None,
    ) -> bool:
        """작업 상태 업데이트"""
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

            stmt = (
                update(ReportJobORM)
                .where(ReportJobORM.id == str(job_id))
                .values(**data)
            )
            await self._session.execute(stmt)
            return True
        except Exception as e:
            logger.error("작업 상태 업데이트 실패: %s", e)
            raise

    async def update_progress(self, job_id: str | UUID, progress: int) -> bool:
        """진행률만 업데이트"""
        return await self.update_status(job_id, "processing", progress=progress)

    async def get_pending_jobs(self, limit: int = 10) -> list[dict[str, Any]]:
        """대기 중인 작업 목록 조회"""
        try:
            stmt = (
                select(ReportJobORM)
                .where(ReportJobORM.status == "pending")
                .order_by(ReportJobORM.created_at.asc())
                .limit(limit)
            )
            result = await self._session.execute(stmt)
            return [self._to_dict(row) for row in result.scalars().all()]
        except Exception as e:
            logger.error("대기 작업 조회 실패: %s", e)
            return []

    async def get_by_branch_and_period(
        self,
        branch_id: int,
        period_start: datetime,
        period_end: datetime,
        status: str | None = None,
    ) -> dict[str, Any] | None:
        """동일 조건의 기존 작업 조회"""
        try:
            stmt = (
                select(ReportJobORM)
                .where(ReportJobORM.branch_id == branch_id)
                .where(ReportJobORM.period_start == period_start.date())
                .where(ReportJobORM.period_end == period_end.date())
            )

            if status:
                stmt = stmt.where(ReportJobORM.status == status)

            stmt = stmt.order_by(ReportJobORM.created_at.desc()).limit(1)
            result = await self._session.execute(stmt)
            row = result.scalar_one_or_none()
            if row:
                return self._to_dict(row)
            return None
        except Exception as e:
            logger.debug("작업 조회 실패: %s", e)
            return None

    async def get_active_by_branch_and_period(
        self,
        branch_id: int,
        period_start: datetime,
        period_end: datetime,
    ) -> dict[str, Any] | None:
        """동일 조건의 활성 작업 조회 (pending 또는 processing)"""
        try:
            stmt = (
                select(ReportJobORM)
                .where(ReportJobORM.branch_id == branch_id)
                .where(ReportJobORM.period_start == period_start.date())
                .where(ReportJobORM.period_end == period_end.date())
                .where(ReportJobORM.status.in_(["pending", "processing"]))
                .order_by(ReportJobORM.created_at.desc())
                .limit(1)
            )
            result = await self._session.execute(stmt)
            row = result.scalar_one_or_none()
            if row:
                return self._to_dict(row)
            return None
        except Exception as e:
            logger.debug("활성 작업 조회 실패: %s", e)
            return None

    async def cleanup_old_jobs(self, days: int = 7) -> int:
        """오래된 작업 정리"""
        try:
            cutoff = utc_now() - timedelta(days=days)

            stmt = (
                delete(ReportJobORM)
                .where(ReportJobORM.created_at < cutoff)
                .where(ReportJobORM.status.in_(["completed", "failed"]))
                .returning(ReportJobORM.id)
            )
            result = await self._session.execute(stmt)
            return len(result.all())
        except Exception as e:
            logger.error("오래된 작업 정리 실패: %s", e)
            return 0

    async def mark_stale_jobs_failed(
        self,
        stale_minutes: int = 30,
        error_message: str = "작업 시간 초과",
    ) -> int:
        """고아 작업을 실패로 마킹 (서버 재시작 복구용)"""
        try:
            cutoff = utc_now() - timedelta(minutes=stale_minutes)

            stmt = (
                update(ReportJobORM)
                .where(ReportJobORM.status == "processing")
                .where(ReportJobORM.updated_at < cutoff)
                .values(status="failed", error_message=error_message)
                .returning(ReportJobORM.id)
            )
            result = await self._session.execute(stmt)
            count = len(result.all())
            if count > 0:
                logger.info("고아 작업 %s개를 failed로 마킹", count)
            return count
        except Exception as e:
            logger.error("고아 작업 복구 실패: %s", e)
            return 0
