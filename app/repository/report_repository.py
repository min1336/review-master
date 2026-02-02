"""리포트 Repository"""

from __future__ import annotations

import json
import logging
from datetime import datetime
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
            ).single().execute()

            return result.data
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
            리포트 목록
        """
        try:
            result = await self._client.table(self.TABLE).select(
                "id, branch_id, branch_name, affiliate_name, "
                "period_start, period_end, total_reviews, created_at, updated_at"
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
        리포트 저장 (upsert)

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
            data = {
                "branch_id": branch_id,
                "branch_name": branch_name,
                "affiliate_name": affiliate_name or "",
                "period_start": period_start.strftime("%Y-%m-%d"),
                "period_end": period_end.strftime("%Y-%m-%d"),
                "total_reviews": total_reviews,
                "report_data": json.dumps(report_data, ensure_ascii=False),
                "updated_at": datetime.now().isoformat(),
            }

            result = await self._client.table(self.TABLE).upsert(
                data,
                on_conflict="branch_id,period_start,period_end"
            ).execute()

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
