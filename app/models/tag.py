from typing import Optional
from datetime import datetime
from pydantic import BaseModel

class Category(BaseModel):
    """categories 테이블 엔티티"""
    id: Optional[int] = None
    name: str
    description: Optional[str] = ""
    color: Optional[str] = "#667eea"
    display_order: Optional[int] = 0
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Tag(BaseModel):
    """tags 테이블 엔티티"""
    id: Optional[int] = None
    name: str
    group_name: Optional[str] = None
    category_id: Optional[int] = None
    color: Optional[str] = "#667eea"
    sentiment: str = "positive"
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # 조인 데이터
    categories: Optional[Category] = None

    class Config:
        from_attributes = True


class KeywordMapping(BaseModel):
    """keyword_tag_mappings 테이블 엔티티"""
    id: Optional[int] = None
    keyword: str
    tag_id: int
    is_auto: bool = True
    confidence: float = 1.0
    created_at: Optional[datetime] = None
    # 조인 데이터
    tags: Optional[Tag] = None

    class Config:
        from_attributes = True


class BranchTag(BaseModel):
    """branch_tags 테이블 엔티티"""
    id: Optional[int] = None
    branch_id: int
    tag_id: int
    period_type: str = "all"
    count: int = 0
    weighted_score: Optional[float] = 0
    rank: Optional[int] = None
    created_at: Optional[datetime] = None
    # 조인 데이터
    tags: Optional[Tag] = None

    class Config:
        from_attributes = True
