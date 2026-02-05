"""동기화 관련 스키마"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class SyncStatusResponse(BaseModel):
    """동기화 상태 응답"""

    last_sync_at: datetime | None = None
    total_reviews: int = 0
    new_reviews: int = 0


class SyncResultResponse(BaseModel):
    """동기화 결과 응답"""

    success: bool
    message: str
    synced_count: int = 0
    new_reviews: int = 0
    duration_seconds: float = 0
    error: str | None = None


class MarkReadRequest(BaseModel):
    """읽음 처리 요청"""

    review_ids: list[int] | None = None  # None이면 전체 읽음 처리


class MarkReadResponse(BaseModel):
    """읽음 처리 응답"""

    success: bool
    marked_count: int = 0


class SchedulerStatusResponse(BaseModel):
    """스케줄러 상태 응답"""

    is_running: bool
    next_run_time: datetime | None = None
    sync_hour: int = 7  # 실행 시간 (시)
    sync_minute: int = 0  # 실행 시간 (분)


class UpdateScheduleTimeRequest(BaseModel):
    """실행 시간 변경 요청"""

    hour: int  # 0~23
    minute: int = 0  # 0~59


class MonthlySchedulerStatusResponse(BaseModel):
    """월간 스케줄러 상태 응답"""

    is_running: bool
    next_run_time: datetime | None = None
    run_day: int = 1  # 실행 일 (1~28)
    run_hour: int = 3  # 실행 시간 (시)
    run_minute: int = 0  # 실행 시간 (분)


class UpdateMonthlyScheduleRequest(BaseModel):
    """월간 스케줄러 시간 변경 요청"""

    day: int = 1  # 1~28
    hour: int = 3  # 0~23
    minute: int = 0  # 0~59


class MonthlyJobResultResponse(BaseModel):
    """월간 작업 결과 응답"""

    success: bool
    message: str
