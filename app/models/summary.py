from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

class Summary(BaseModel):
    """branch_summaries 테이블 엔티티"""
    id: Optional[int] = None
    branch_id: int
    branch_name: Optional[str] = None
    region: Optional[str] = None
    status: str = "draft"
    review_count: Optional[int] = 0
    avg_rating: Optional[float] = None
    keywords: Optional[List[str]] = None
    keyword_1: Optional[str] = None
    keyword_2: Optional[str] = None
    keyword_3: Optional[str] = None
    summary_all: Optional[str] = None
    summary_1y: Optional[str] = None
    summary_6m: Optional[str] = None
    summary_3m: Optional[str] = None
    summary_1m: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
