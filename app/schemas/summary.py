"""요약 관련 Pydantic 모델"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class SummaryUpdate(BaseModel):
    """요약 수정 요청"""
    region: Optional[str] = None
    keywords: Optional[List[str]] = None
    summary_all: Optional[str] = None
    summary_1y: Optional[str] = None
    summary_6m: Optional[str] = None
    summary_3m: Optional[str] = None
    summary_1m: Optional[str] = None


class StatusUpdate(BaseModel):
    """상태 변경 요청"""
    status: str = Field(..., pattern="^(draft|approved|published)$")


class RegenerateRequest(BaseModel):
    """AI 요약 재생성 요청"""
    period: str = Field("all", pattern="^(all|1y|6m|3m|1m)$")
