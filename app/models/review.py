from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

class Review(BaseModel):
    """recent_reviews 테이블 엔티티"""
    id: Optional[int] = None
    branch_id: int
    review_id: Optional[str] = None
    content: Optional[str] = None
    rating: Optional[float] = None
    sentiment: Optional[str] = None
    keywords: Optional[List[str]] = None
    review_date: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
