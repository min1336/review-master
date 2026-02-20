"""
DB 엔티티 Pydantic 모델
Repository에서 반환되는 타입으로 사용
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class Summary(BaseModel):
    """branch_summaries 테이블 엔티티"""

    id: int | None = None
    branch_id: int
    branch_name: str | None = None
    region: str | None = None
    status: str | None = None
    review_count: int | None = 0
    avg_rating: float | None = None
    keywords: list[str] | None = None
    keyword_1: str | None = None
    keyword_2: str | None = None
    keyword_3: str | None = None
    summary_all: str | None = None
    summary_1y: str | None = None
    summary_6m: str | None = None
    summary_3m: str | None = None
    summary_1m: str | None = None
    pending_summaries: dict[str, Any] | None = None  # AI 생성 대기 중인 요약
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class Category(BaseModel):
    """categories 테이블 엔티티"""

    id: int | None = None
    name: str
    description: str | None = ""
    color: str | None = "#667eea"
    display_order: int | None = 0
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class Tag(BaseModel):
    """tags 테이블 엔티티"""

    id: int | None = None
    name: str
    group_name: str | None = None
    category_id: int | None = None
    color: str | None = "#667eea"
    sentiment: str = "positive"
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # 조인 데이터
    categories: Category | None = None

    class Config:
        from_attributes = True


class KeywordMapping(BaseModel):
    """keyword_tag_mappings 테이블 엔티티"""

    id: int | None = None
    keyword: str
    tag_id: int
    is_auto: bool = True
    confidence: float = 1.0
    created_at: datetime | None = None
    # 조인 데이터
    tags: Tag | None = None

    class Config:
        from_attributes = True


class BranchTag(BaseModel):
    """branch_tags 테이블 엔티티"""

    id: int | None = None
    branch_id: int
    tag_id: int
    period_type: str = "all"
    count: int = 0
    weighted_score: float | None = 0
    rank: int | None = None
    created_at: datetime | None = None
    # 조인 데이터
    tags: Tag | None = None

    class Config:
        from_attributes = True


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


class Affiliate(BaseModel):
    """affiliates 테이블 엔티티"""

    id: int | None = None
    branch_id: int
    name: str | None = None
    address: str | None = None
    phone: str | None = None
    region: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
