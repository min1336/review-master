"""태그/카테고리 관련 Pydantic 모델"""
from typing import Optional, List
from pydantic import BaseModel, Field


class TagCreate(BaseModel):
    """태그 생성 요청"""
    name: str
    group_name: Optional[str] = None
    color: Optional[str] = "#667eea"
    sentiment: str = Field("positive", pattern="^(positive|negative|neutral)$")


class TagUpdate(BaseModel):
    """태그 수정 요청"""
    name: Optional[str] = None
    group_name: Optional[str] = None
    color: Optional[str] = None
    sentiment: Optional[str] = None
    is_active: Optional[bool] = None


class CategoryCreate(BaseModel):
    """카테고리 생성 요청"""
    name: str
    description: Optional[str] = ""
    color: Optional[str] = "#667eea"
    display_order: Optional[int] = 0


class CategoryUpdate(BaseModel):
    """카테고리 수정 요청"""
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    display_order: Optional[int] = None


class KeywordMappingCreate(BaseModel):
    """키워드 매핑 생성"""
    keyword: str
    tag_id: int
    is_auto: bool = False


class BulkMappingRequest(BaseModel):
    """매핑 일괄 생성"""
    mappings: List[KeywordMappingCreate]


class TagAnalysisRequest(BaseModel):
    """태그 분석 요청"""
    review: str = Field(..., min_length=1)
