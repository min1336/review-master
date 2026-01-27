"""공통 응답 모델"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SuccessResponse(BaseModel):
    """공통 성공 응답"""

    success: bool = True
    message: str | None = None
    data: Any | None = None


class ErrorResponse(BaseModel):
    """공통 에러 응답"""

    error: str
    detail: str | None = None


class CleanupRequest(BaseModel):
    """리뷰 정리 요청"""

    days: int = 30
    max_per_branch: int = 30
