"""리포트 Repository"""

from __future__ import annotations

import logging
from datetime import datetime

from core.timezone import utc_now
from typing import Any

from supabase._async.client import AsyncClient

from .base import BaseRepository

logger = logging.getLogger(__name__)


class ReportRepository(BaseRepository):
    """리포트 저장/조회 Repository"""

    TABLE = "branch_reports"

    @property
    def table_name(self) -> str:
        return self.TABLE

    async def get_by_branch_and_period(
        self,
        branch_id: int,
        period_start: datetime,
        period_end: datetime,
    ) -> dict | None:
        """
        특정 지점의 기간별 리포트 조회

        Args:
            branch_id: 지점 ID
            period_start: 시작일
            period_end: 종료일

        Returns:
            리포트 데이터 또는 None
        """
        try:
            result = await self._client.table(self.TABLE).select("*").eq(
                "branch_id", branch_id
            ).eq(
                "period_start", period_start.strftime("%Y-%m-%d")
            ).eq(
                "period_end", period_end.strftime("%Y-%m-%d")
            ).order(
                "version", desc=True
            ).limit(1).execute()

            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.debug(f"리포트 조회 실패 (없음): {e}")
            return None

    async def get_latest_by_branch(self, branch_id: int) -> dict | None:
        """
        특정 지점의 최신 리포트 조회

        Args:
            branch_id: 지점 ID

        Returns:
            최신 리포트 데이터 또는 None
        """
        try:
            result = await self._client.table(self.TABLE).select("*").eq(
                "branch_id", branch_id
            ).order(
                "created_at", desc=True
            ).limit(1).execute()

            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"최신 리포트 조회 실패: {e}")
            return None

    async def get_all_by_branch(
        self,
        branch_id: int,
        limit: int = 10,
    ) -> list[dict]:
        """
        특정 지점의 모든 리포트 목록 조회

        Args:
            branch_id: 지점 ID
            limit: 조회 개수

        Returns:
            리포트 목록 (is_viewed 포함)
        """
        try:
            result = await self._client.table(self.TABLE).select(
                "id, branch_id, branch_name, affiliate_name, "
                "period_start, period_end, total_reviews, version, "
                "is_viewed, viewed_at, created_at, updated_at"
            ).eq(
                "branch_id", branch_id
            ).order(
                "created_at", desc=True
            ).limit(limit).execute()

            return result.data or []
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
        """
        리포트 저장 (버전 관리)

        동일 기간에 이미 리포트가 있으면 version을 증가시켜 히스토리 유지

        Args:
            branch_id: 지점 ID
            branch_name: 지점명
            affiliate_name: 업체명
            period_start: 시작일
            period_end: 종료일
            total_reviews: 총 리뷰 수
            report_data: 전체 리포트 데이터

        Returns:
            저장된 리포트 데이터
        """
        try:
            # 기존 최신 버전 조회
            existing = await self._client.table(self.TABLE).select("version").eq(
                "branch_id", branch_id
            ).eq(
                "period_start", period_start.strftime("%Y-%m-%d")
            ).eq(
                "period_end", period_end.strftime("%Y-%m-%d")
            ).order("version", desc=True).limit(1).execute()

            next_version = 1
            if existing.data:
                next_version = (existing.data[0].get("version", 0) or 0) + 1

            data = {
                "branch_id": branch_id,
                "branch_name": branch_name,
                "affiliate_name": affiliate_name or "",
                "period_start": period_start.strftime("%Y-%m-%d"),
                "period_end": period_end.strftime("%Y-%m-%d"),
                "total_reviews": total_reviews,
                "report_data": report_data,
                "version": next_version,
                "is_viewed": False,  # 신규 리포트는 미조회 상태
                "updated_at": utc_now().isoformat(),
            }

            result = await self._client.table(self.TABLE).insert(data).execute()

            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"리포트 저장 실패: {e}")
            raise

    async def delete(self, report_id: int) -> bool:
        """
        리포트 삭제

        Args:
            report_id: 리포트 ID

        Returns:
            삭제 성공 여부
        """
        try:
            await self._client.table(self.TABLE).delete().eq(
                "id", report_id
            ).execute()
            return True
        except Exception as e:
            logger.error(f"리포트 삭제 실패: {e}")
            return False

    async def mark_as_viewed(self, report_id: int) -> bool:
        """
        리포트 조회 표시

        Args:
            report_id: 리포트 ID

        Returns:
            성공 여부
        """
        try:
            await self._client.table(self.TABLE).update({
                "is_viewed": True,
                "viewed_at": utc_now().isoformat(),
            }).eq("id", report_id).execute()
            return True
        except Exception as e:
            logger.error(f"리포트 조회 표시 실패: {e}")
            return False

    async def get_unviewed_count(self, branch_id: int | None = None) -> int:
        """
        미조회 리포트 개수 조회

        Args:
            branch_id: 지점 ID (None이면 전체)

        Returns:
            미조회 리포트 개수
        """
        try:
            query = self._client.table(self.TABLE).select("id", count="exact").eq(
                "is_viewed", False
            )
            if branch_id:
                query = query.eq("branch_id", branch_id)

            result = await query.execute()
            return result.count or 0
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
        """
        특정 기간의 리포트 히스토리 조회 (버전별)

        Args:
            branch_id: 지점 ID
            period_start: 시작일
            period_end: 종료일
            limit: 조회 개수

        Returns:
            리포트 히스토리 목록
        """
        try:
            result = await self._client.table(self.TABLE).select(
                "id, branch_id, branch_name, version, total_reviews, "
                "is_viewed, viewed_at, created_at, updated_at"
            ).eq(
                "branch_id", branch_id
            ).eq(
                "period_start", period_start.strftime("%Y-%m-%d")
            ).eq(
                "period_end", period_end.strftime("%Y-%m-%d")
            ).order(
                "version", desc=True
            ).limit(limit).execute()

            return result.data or []
        except Exception as e:
            logger.error(f"리포트 히스토리 조회 실패: {e}")
            return []

    async def delete_by_branch_and_period(
        self,
        branch_id: int,
        period_start: datetime,
        period_end: datetime,
    ) -> bool:
        """
        특정 지점의 기간별 리포트 삭제

        Args:
            branch_id: 지점 ID
            period_start: 시작일
            period_end: 종료일

        Returns:
            삭제 성공 여부
        """
        try:
            await self._client.table(self.TABLE).delete().eq(
                "branch_id", branch_id
            ).eq(
                "period_start", period_start.strftime("%Y-%m-%d")
            ).eq(
                "period_end", period_end.strftime("%Y-%m-%d")
            ).execute()
            return True
        except Exception as e:
            logger.error(f"리포트 삭제 실패 (branch: {branch_id}, period: {period_start} ~ {period_end}): {e}")
            return False
