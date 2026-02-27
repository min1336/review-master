"""파이프라인 콘솔 관련 스키마"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


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
