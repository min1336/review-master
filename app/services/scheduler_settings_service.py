"""스케줄러 설정 Service"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from core.timezone import utc_now
from typing import Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# 주기별 일수 매핑
CYCLE_DAYS = {
    "weekly": 7,
    "biweekly": 14,
    "monthly": 30,
}

SummaryCycle = Literal["weekly", "biweekly", "monthly"]


class SchedulerSettingsDTO(BaseModel):
    """스케줄러 설정 DTO"""

    branch_id: int
    summary_cycle: SummaryCycle = "monthly"
    min_reviews: int = 30
    auto_approve: bool = False
    last_summary_at: datetime | None = None
    next_summary_at: datetime | None = None

    class Config:
        from_attributes = True


class SchedulerSettingsService:
    """업체별 스케줄러 설정 Service"""

    def __init__(self, settings_repo) -> None:
        self.settings_repo = settings_repo

    async def get_settings(self, branch_id: int) -> SchedulerSettingsDTO | None:
        """업체별 설정 조회"""
        data = await self.settings_repo.get_by_branch_id(branch_id)

        if not data:
            return None

        return SchedulerSettingsDTO(
            branch_id=data["branch_id"],
            summary_cycle=data.get("summary_cycle", "monthly"),
            min_reviews=data.get("min_reviews", 30),
            auto_approve=data.get("auto_approve", False),
            last_summary_at=_parse_datetime(data.get("last_summary_at")),
            next_summary_at=_parse_datetime(data.get("next_summary_at")),
        )

    async def update_settings(
        self,
        branch_id: int,
        summary_cycle: SummaryCycle | None = None,
        min_reviews: int | None = None,
        auto_approve: bool | None = None,
    ) -> SchedulerSettingsDTO | None:
        """설정 업데이트"""
        # 기존 설정 조회
        existing = await self.settings_repo.get_by_branch_id(branch_id)

        data = {
            "branch_id": branch_id,
            "summary_cycle": summary_cycle or (existing or {}).get("summary_cycle", "monthly"),
            "min_reviews": min_reviews if min_reviews is not None else (existing or {}).get("min_reviews", 30),
            "auto_approve": auto_approve if auto_approve is not None else (existing or {}).get("auto_approve", False),
        }

        # 주기 변경 시 다음 실행 시간 재계산
        if summary_cycle and existing:
            last_summary = _parse_datetime(existing.get("last_summary_at"))
            if last_summary:
                data["next_summary_at"] = self._calculate_next_summary(
                    last_summary, summary_cycle
                ).isoformat()

        result = await self.settings_repo.upsert(data)

        if not result:
            return None

        return await self.get_settings(branch_id)

    async def create_default_settings(self, branch_id: int) -> SchedulerSettingsDTO | None:
        """기본 설정 생성"""
        data = {
            "branch_id": branch_id,
            "summary_cycle": "monthly",
            "min_reviews": 30,
            "auto_approve": False,
        }

        result = await self.settings_repo.upsert(data)

        if not result:
            return None

        return await self.get_settings(branch_id)

    async def mark_summary_generated(self, branch_id: int) -> bool:
        """요약 생성 완료 표시"""
        # 현재 설정 조회
        settings = await self.get_settings(branch_id)

        if not settings:
            # 기본 설정으로 생성
            settings = await self.create_default_settings(branch_id)
            if not settings:
                return False

        now = utc_now()
        next_summary = self._calculate_next_summary(now, settings.summary_cycle)

        return await self.settings_repo.update_last_summary(
            branch_id=branch_id,
            last_summary_at=now,
            next_summary_at=next_summary,
        )

    def _calculate_next_summary(
        self, from_date: datetime, cycle: SummaryCycle
    ) -> datetime:
        """다음 요약 생성 시간 계산"""
        days = CYCLE_DAYS.get(cycle, 30)
        return from_date + timedelta(days=days)

    async def get_branches_due_for_summary(self) -> list[SchedulerSettingsDTO]:
        """요약 생성이 필요한 업체 목록"""
        data_list = await self.settings_repo.get_branches_due_for_summary()

        return [
            SchedulerSettingsDTO(
                branch_id=d["branch_id"],
                summary_cycle=d.get("summary_cycle", "monthly"),
                min_reviews=d.get("min_reviews", 30),
                auto_approve=d.get("auto_approve", False),
                last_summary_at=_parse_datetime(d.get("last_summary_at")),
                next_summary_at=_parse_datetime(d.get("next_summary_at")),
            )
            for d in data_list
        ]


def _parse_datetime(value: str | None) -> datetime | None:
    """datetime 파싱"""
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
