from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class SentimentStats(BaseModel):
    """sentiment_stats 테이블 엔티티"""

    id: int | None = None
    branch_id: int
    period_type: str = "all"
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    total_count: int = 0
    positive_ratio: float | None = None
    negative_ratio: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
