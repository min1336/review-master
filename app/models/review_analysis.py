"""review_analysis 테이블 Pydantic 모델"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ReviewAnalysis(BaseModel):
    """review_analysis 테이블 엔티티"""

    review_id: int  # PK, Athena 매칭용
    branch_id: int
    content: str | None = None
    sentiment: str | None = None  # positive/neutral/negative
    car_model: str | None = None
    review_date: datetime | None = None
    rating_service: Decimal | None = None
    is_new: bool = True
    is_deleted: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
