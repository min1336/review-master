from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Review(BaseModel):
    """branch_reviews 테이블 엔티티"""

    id: int | None = None
    branch_id: int
    review_id: str | None = None
    content: str | None = None
    rating: float | None = None
    sentiment: str | None = None
    keywords: list[str] | None = None
    review_date: datetime | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True
