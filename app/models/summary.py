from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class Summary(BaseModel):
    """branch_summaries 테이블 엔티티"""

    id: int | None = None
    branch_id: int
    branch_name: str | None = None
    region: str | None = None
    status: str | None = None
    review_count: int = 0
    avg_rating: float | None = None
    keywords: list[str] | None = None
    keyword_1: str | None = None
    keyword_2: str | None = None
    keyword_3: str | None = None
    summary_all: str | None = None
    summary_1y: str | None = None
    summary_6m: str | None = None
    summary_3m: str | None = None
    summary_1m: str | None = None
    pending_summaries: dict[str, Any] | None = None  # AI 생성 대기 중인 요약
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
