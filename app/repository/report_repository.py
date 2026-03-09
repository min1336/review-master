"""리포트 Repository"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.timezone import utc_now

from sqlalchemy.ext.asyncio import AsyncSession

from .orm_models import BranchReportORM

logger = logging.getLogger(__name__)


class ReportRepository:
    """리포트 저장/조회 Repository"""

    def __init__(self, session: AsyncSession):
        self._session = session

    @staticmethod
    def _to_dict(row: BranchReportORM) -> dict[str, Any]:
        return {c.key: getattr(row, c.key) for c in row.__table__.columns}

    async def get_by_branch_and_period(
        self,
        branch_id: int,
        period_start: datetime,
        period_end: datetime,
    ) -> dict | None:
        """특정 지점의 기간별 리포트 조회"""
        try:
            stmt = (
                select(BranchReportORM)
                .where(BranchReportORM.branch_id == branch_id)
                .where(BranchReportORM.period_start == period_start.date())
                .where(BranchReportORM.period_end == period_end.date())
                .order_by(BranchReportORM.version.desc())
                .limit(1)
            )
            result = await self._session.execute(stmt)
            row = result.scalar_one_or_none()
            if row:
                return self._to_dict(row)
            return None
        except Exception as e:
            logger.debug(f"리포트 조회 실패 (없음): {e}")
            return None

    async def get_latest_by_branch(self, branch_id: int) -> dict | None:
        """특정 지점의 최신 리포트 조회"""
        try:
            stmt = (
                select(BranchReportORM)
                .where(BranchReportORM.branch_id == branch_id)
                .order_by(BranchReportORM.created_at.desc())
                .limit(1)
            )
            result = await self._session.execute(stmt)
            row = result.scalar_one_or_none()
            if row:
                return self._to_dict(row)
            return None
        except Exception as e:
            logger.error(f"최신 리포트 조회 실패: {e}")
            return None

    async def get_all_by_branch(
        self,
        branch_id: int,
        limit: int = 10,
    ) -> list[dict]:
        """특정 지점의 모든 리포트 목록 조회"""
        try:
            stmt = (
                select(
                    BranchReportORM.id,
                    BranchReportORM.branch_id,
                    BranchReportORM.branch_name,
                    BranchReportORM.affiliate_name,
                    BranchReportORM.period_start,
                    BranchReportORM.period_end,
                    BranchReportORM.total_reviews,
                    BranchReportORM.version,
                    BranchReportORM.is_viewed,
                    BranchReportORM.viewed_at,
                    BranchReportORM.created_at,
                    BranchReportORM.updated_at,
                )
                .where(BranchReportORM.branch_id == branch_id)
                .order_by(BranchReportORM.created_at.desc())
                .limit(limit)
            )
            result = await self._session.execute(stmt)
            return [dict(row._mapping) for row in result.all()]
        except Exception as e:
            logger.error(f"리포트 목록 조회 실패: {e}")
            return []

    async def save(
        self,
        branch_id: int,
        branch_name: str,
        affiliate_name: str,
        period_start: datetime,
        period_end: datetime,
        total_reviews: int,
        report_data: dict[str, Any],
    ) -> dict | None:
        """리포트 저장 (upsert — 동일 기간 덮어쓰기)"""
        try:
            data = {
                "branch_id": branch_id,
                "branch_name": branch_name,
                "affiliate_name": affiliate_name or "",
                "period_start": period_start.date() if hasattr(period_start, 'date') else period_start,
                "period_end": period_end.date() if hasattr(period_end, 'date') else period_end,
                "total_reviews": total_reviews,
                "report_data": report_data,
                "version": 1,
                "is_viewed": False,
                "updated_at": utc_now(),
            }

            stmt = (
                pg_insert(BranchReportORM.__table__)
                .values(**data)
                .on_conflict_do_update(
                    index_elements=["branch_id", "period_start", "period_end"],
                    set_={
                        "branch_name": data["branch_name"],
                        "affiliate_name": data["affiliate_name"],
                        "total_reviews": data["total_reviews"],
                        "report_data": data["report_data"],
                        "version": data["version"],
                        "is_viewed": data["is_viewed"],
                        "updated_at": data["updated_at"],
                    },
                )
                .returning(BranchReportORM.__table__)
            )
            result = await self._session.execute(stmt)
            row = result.mappings().one_or_none()
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"리포트 저장 실패: {e}")
            raise

    async def delete(self, report_id: int) -> bool:
        """리포트 삭제"""
        try:
            stmt = (
                delete(BranchReportORM)
                .where(BranchReportORM.id == report_id)
            )
            result = await self._session.execute(stmt)
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"리포트 삭제 실패: {e}")
            raise

    async def mark_as_viewed(self, report_id: int) -> bool:
        """리포트 조회 표시"""
        try:
            stmt = (
                update(BranchReportORM)
                .where(BranchReportORM.id == report_id)
                .values(is_viewed=True, viewed_at=utc_now())
            )
            await self._session.execute(stmt)
            return True
        except Exception as e:
            logger.error(f"리포트 조회 표시 실패: {e}")
            return False

    async def get_unviewed_count(self, branch_id: int | None = None) -> int:
        """미조회 리포트 개수 조회"""
        try:
            stmt = (
                select(func.count())
                .select_from(BranchReportORM)
                .where(BranchReportORM.is_viewed == False)  # noqa: E712
            )
            if branch_id:
                stmt = stmt.where(BranchReportORM.branch_id == branch_id)

            result = await self._session.execute(stmt)
            return result.scalar_one()
        except Exception as e:
            logger.error(f"미조회 리포트 개수 조회 실패: {e}")
            return 0

    async def get_report_history(
        self,
        branch_id: int,
        period_start: datetime,
        period_end: datetime,
        limit: int = 10,
    ) -> list[dict]:
        """특정 기간의 리포트 히스토리 조회 (버전별)"""
        try:
            stmt = (
                select(
                    BranchReportORM.id,
                    BranchReportORM.branch_id,
                    BranchReportORM.branch_name,
                    BranchReportORM.version,
                    BranchReportORM.total_reviews,
                    BranchReportORM.is_viewed,
                    BranchReportORM.viewed_at,
                    BranchReportORM.created_at,
                    BranchReportORM.updated_at,
                )
                .where(BranchReportORM.branch_id == branch_id)
                .where(BranchReportORM.period_start == period_start.date())
                .where(BranchReportORM.period_end == period_end.date())
                .order_by(BranchReportORM.version.desc())
                .limit(limit)
            )
            result = await self._session.execute(stmt)
            return [dict(row._mapping) for row in result.all()]
        except Exception as e:
            logger.error(f"리포트 히스토리 조회 실패: {e}")
            return []

    async def delete_by_branch_and_period(
        self,
        branch_id: int,
        period_start: datetime,
        period_end: datetime,
    ) -> bool:
        """특정 지점의 기간별 리포트 삭제"""
        try:
            stmt = (
                delete(BranchReportORM)
                .where(BranchReportORM.branch_id == branch_id)
                .where(BranchReportORM.period_start == period_start.date())
                .where(BranchReportORM.period_end == period_end.date())
            )
            await self._session.execute(stmt)
            return True
        except Exception as e:
            logger.error(
                f"리포트 삭제 실패 (branch: {branch_id}, "
                f"period: {period_start} ~ {period_end}): {e}"
            )
            return False
