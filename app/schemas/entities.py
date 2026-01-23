"""
DB 엔티티 Pydantic 모델
Repository에서 반환되는 타입으로 사용
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


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
    pending_summaries: Optional[Dict[str, Any]] = None  # AI 생성 대기 중인 요약
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


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


class Affiliate(BaseModel):
    """affiliates 테이블 엔티티"""
    id: Optional[int] = None
    branch_id: int
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    region: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
