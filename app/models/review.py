from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Review(BaseModel):
    """branch_reviews 테이블 엔티티"""

    id: int | None = None
    branch_id: int
    review_id: str | None = None
    content: str | None = None
    rating: float | None = None
    rating_service: float | None = None
    rating_car: float | None = None
    rating_convenience: float | None = None
    sentiment: str | None = None
    keywords: list[str] | None = None
    review_date: datetime | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
