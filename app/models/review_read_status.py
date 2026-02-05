from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ReviewReadStatus(BaseModel):
    """review_read_status 테이블 엔티티"""

    id: int | None = None
    review_id: str
    read_at: datetime | None = None
    read_by: str | None = None

    class Config:
        from_attributes = True
