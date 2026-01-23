from typing import Optional
from datetime import datetime
from pydantic import BaseModel

class SentimentStats(BaseModel):
    """sentiment_stats 테이블 엔티티"""
    id: Optional[int] = None
    branch_id: int
    period_type: str = "all"
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    total_count: int = 0
    positive_ratio: Optional[float] = None
    negative_ratio: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
