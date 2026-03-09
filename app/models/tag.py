from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


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

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


class KeywordMapping(BaseModel):
    """keyword_mappings 테이블 엔티티"""

    id: int | None = None
    keyword: str
    tag_id: int
    is_auto: bool = True
    confidence: float = 1.0
    created_at: datetime | None = None
    # 조인 데이터
    tags: Tag | None = None

    model_config = ConfigDict(from_attributes=True)


class BranchTag(BaseModel):
    """branch_tags 테이블 엔티티"""

    id: int | None = None
    branch_id: int
    tag_id: int
    period_type: str = "all"
    count: int = 0
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    weighted_score: float | None = 0
    rank: int | None = None
    # 조인 데이터
    tags: Tag | None = None

    model_config = ConfigDict(from_attributes=True)
