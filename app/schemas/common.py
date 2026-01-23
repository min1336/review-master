"""공통 응답 모델"""
from typing import Any, Optional
from pydantic import BaseModel


class SuccessResponse(BaseModel):
    """공통 성공 응답"""
    success: bool = True
    message: Optional[str] = None
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    """공통 에러 응답"""
    error: str
    detail: Optional[str] = None
