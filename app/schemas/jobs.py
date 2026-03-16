"""비동기 작업(동기화, 업로드, 파이프라인, 실시간) 관련 스키마"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ── Sync ─────────────────────────────────────────────────────

class SyncResultResponse(BaseModel):
    """동기화 결과 응답"""

    success: bool
    message: str
    synced_count: int = 0
    new_reviews: int = 0
    duration_seconds: float = 0
    error: str | None = None


class SyncRequest(BaseModel):
    """동기화 요청 (날짜 범위 지정 가능)"""

    date_from: str | None = None  # YYYY-MM-DD, None이면 last_sync_at 사용
    date_to: str | None = None    # YYYY-MM-DD, None이면 제한 없음


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


# ── Upload ───────────────────────────────────────────────────

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


# ── Pipeline ─────────────────────────────────────────────────

class FullPipelineRequest(BaseModel):
    """전체 재처리 파이프라인 요청"""

    date_from: str | None = Field(None, description="시작일 (YYYY-MM-DD)")
    date_to: str | None = Field(None, description="종료일 (YYYY-MM-DD)")
    chunk_size: int = Field(500, ge=100, le=2000, description="청크 크기")


class PipelineJobStatusResponse(BaseModel):
    """파이프라인 작업 상태 응답"""

    job_id: str
    status: str  # pending | processing | completed | failed
    progress: int = 0  # 0-100
    message: str = ""
    total_reviews: int = 0
    processed_reviews: int = 0
    current_chunk: int = 0
    total_chunks: int = 0
    error: str | None = None
    result: dict | None = None
    created_at: datetime | None = None


# ── Realtime ─────────────────────────────────────────────────

class ReviewInput(BaseModel):
    """리뷰 입력 스키마"""

    branch_id: int = Field(..., description="업체 ID")
    review_id: int | None = Field(default=None, description="리뷰 ID (branch_reviews.review_id)")
    content: str = Field(default="", description="리뷰 내용")
    rating_service: float | None = Field(default=None, ge=1.0, le=5.0, description="서비스 평점 (1-5)")
    rating_car: float | None = Field(default=None, ge=1.0, le=5.0, description="차량 평점 (1-5)")
    rating_convenience: float | None = Field(default=None, ge=1.0, le=5.0, description="편의성 평점 (1-5)")


class ProcessResult(BaseModel):
    """처리 결과 스키마"""

    branch_id: int
    sentiment: str
    tags: list[dict]
    saved: bool
    error: str | None = None
