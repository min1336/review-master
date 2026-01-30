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
    interval_minutes: int = 0
    min_interval: int = 5
    max_interval: int = 30


class UpdateIntervalRequest(BaseModel):
    """간격 변경 요청"""

    interval_minutes: int
