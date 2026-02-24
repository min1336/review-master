"""태그/카테고리 관련 Pydantic 모델"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TagCreate(BaseModel):
    """태그 생성 요청"""

    name: str
    group_name: str | None = None
    color: str | None = "#667eea"
    sentiment: str = Field("positive", pattern="^(positive|negative|neutral)$")


class TagUpdate(BaseModel):
    """태그 수정 요청"""

    name: str | None = None
    group_name: str | None = None
    color: str | None = None
    sentiment: str | None = None
    is_active: bool | None = None


class CategoryCreate(BaseModel):
    """카테고리 생성 요청"""

    name: str
    description: str | None = ""
    color: str | None = "#667eea"
    display_order: int | None = 0


class CategoryUpdate(BaseModel):
    """카테고리 수정 요청"""

    name: str | None = None
    description: str | None = None
    color: str | None = None
    display_order: int | None = None


class KeywordMappingCreate(BaseModel):
    """키워드 매핑 생성"""

    keyword: str
    tag_id: int
    is_auto: bool = False


class BulkMappingRequest(BaseModel):
    """매핑 일괄 생성"""

    mappings: list[KeywordMappingCreate]
