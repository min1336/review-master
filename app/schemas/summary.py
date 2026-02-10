"""요약 관련 Pydantic 모델"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SummaryUpdate(BaseModel):
    """요약 수정 요청"""

    region: str | None = None
    keywords: list[str] | None = None
    summary_all: str | None = None
    summary_1y: str | None = None
    summary_6m: str | None = None
    summary_3m: str | None = None
    summary_1m: str | None = None


class StatusUpdate(BaseModel):
    """상태 변경 요청"""

    status: str = Field(..., pattern="^(draft|approved|published)$")


class RegenerateRequest(BaseModel):
    """AI 요약 재생성 요청 (apply-pending/discard-pending용)"""

    period: str = Field("all", pattern="^(all|1y|6m|3m|1m)$")
