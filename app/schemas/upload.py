"""엑셀/CSV 업로드 관련 스키마"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class UploadRowError(BaseModel):
    """업로드 행 오류"""

    row: int
    error: str


class UploadResultResponse(BaseModel):
    """업로드 처리 결과"""

    success: bool
    uploaded_count: int = 0
    upserted_count: int = 0
    processed_count: int = 0
    failed_count: int = 0
    duration_seconds: float = 0
    errors: list[UploadRowError] = []


class UploadJobStatusResponse(BaseModel):
    """비동기 업로드 작업 상태 응답"""

    job_id: str
    status: str  # pending | processing | completed | failed
    progress: int  # 0-100
    message: str = ""
    total_rows: int = 0
    error: str | None = None
    result: UploadResultResponse | None = None
    created_at: datetime | None = None
