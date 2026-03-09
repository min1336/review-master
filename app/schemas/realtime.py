"""실시간 리뷰 처리 스키마"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReviewInput(BaseModel):
    """리뷰 입력 스키마"""

    branch_id: int = Field(..., description="업체 ID")
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
