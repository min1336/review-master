"""동기화 관련 스키마"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


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


class SyncJobStatusResponse(BaseModel):
    """비동기 동기화 작업 상태 응답"""

    job_id: str
    status: str  # pending | processing | completed | failed
    progress: int  # 0-100
    message: str = ""
    error: str | None = None
    result: SyncResultResponse | None = None
    created_at: datetime | None = None
