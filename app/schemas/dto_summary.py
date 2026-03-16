"""Summary 관련 DTO"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from core.timezone import utc_now


class SummaryRequestDTO(BaseModel):
    """LLM 요약 요청 DTO"""

    branch_id: int
    branch_name: str
    keywords: list[str]
    representative_reviews: list[str]
    review_count: int
    avg_sentiment_score: float = 0.0
    positive_count: int = 0
    negative_count: int = 0

    def to_prompt_context(self) -> str:
        """프롬프트용 컨텍스트 문자열 생성"""
        keywords_str = ", ".join(self.keywords[:10])
        reviews_str = "\n".join(f"- {r}" for r in self.representative_reviews[:5])

        return f"""
지점: {self.branch_name}
리뷰 수: {self.review_count}개
평균 감정점수: {self.avg_sentiment_score:.2f}
주요 키워드: {keywords_str}

대표 리뷰:
{reviews_str}
"""


class SummaryResponseDTO(BaseModel):
    """LLM 요약 응답 DTO"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    branch_id: int
    summary: str
    model: str
    tokens_used: int = 0
    is_valid: bool = True
    validation_errors: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utc_now)

    @model_serializer
    def _serialize(self) -> dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "summary": self.summary,
            "model": self.model,
            "tokens_used": self.tokens_used,
            "is_valid": self.is_valid,
            "validation_errors": self.validation_errors,
            "generated_at": self.generated_at.isoformat(),
        }


class SummaryStatsDTO(BaseModel):
    """요약 통계 DTO"""

    total: int
    total_reviews: int


class RegionStatsDTO(BaseModel):
    """지역별 통계 DTO"""

    region: str
    count: int
    avg_rating: float
    total_reviews: int


class RatingDistributionDTO(BaseModel):
    """평점 분포 DTO"""

    model_config = ConfigDict(populate_by_name=True)

    range_4_5_to_5_0: int = Field(0, serialization_alias="4.5-5.0")
    range_4_0_to_4_5: int = Field(0, serialization_alias="4.0-4.5")
    range_3_5_to_4_0: int = Field(0, serialization_alias="3.5-4.0")
    range_3_0_to_3_5: int = Field(0, serialization_alias="3.0-3.5")
    range_below_3_0: int = Field(0, serialization_alias="<3.0")


class RatingStatsDTO(BaseModel):
    """평점 분포 통계 DTO"""

    min: float
    max: float
    avg: float
    total: int
    distribution: RatingDistributionDTO

    @model_serializer
    def _serialize(self) -> dict[str, Any]:
        return {
            "min": self.min,
            "max": self.max,
            "avg": self.avg,
            "total": self.total,
            "distribution": self.distribution.model_dump(by_alias=True),
        }


class SummaryWithTagsDTO(BaseModel):
    """요약 + 태그 조합 DTO"""

    summary: dict[str, Any] | None
    tags: list[dict[str, Any]]


class PendingSummaryResultDTO(BaseModel):
    """대기 중인 요약 적용/취소 결과 DTO"""

    period: str
    applied: str | None = None
    discarded: str | None = None

    @model_serializer
    def _serialize(self) -> dict[str, Any]:
        result: dict[str, Any] = {"period": self.period}
        if self.applied is not None:
            result["applied"] = self.applied
        if self.discarded is not None:
            result["discarded"] = self.discarded
        return result


class TagSentimentCountDTO(BaseModel):
    """태그별 감정 카운트 DTO"""

    name: str
    total: int
    positive: int
    negative: int
    neutral: int = Field(0, exclude=True)


class ReviewOutputDTO(BaseModel):
    """리뷰 출력 DTO"""

    id: str | None
    date: datetime | str | None
    content: str
    keywords: list[str]
    tag_sentiments: str

    @model_serializer
    def _serialize(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "date": (
                self.date.isoformat() if isinstance(self.date, datetime) else self.date
            ),
            "content": self.content,
            "keywords": self.keywords,
            "tag_sentiments": self.tag_sentiments,
        }


class SummariesOutputDTO(BaseModel):
    """기간별 요약 출력 DTO"""

    model_config = ConfigDict(populate_by_name=True)

    summary_1m: str = Field("", serialization_alias="1m")
    summary_3m: str = Field("", serialization_alias="3m")
    summary_6m: str = Field("", serialization_alias="6m")
    summary_1y: str = Field("", serialization_alias="1y")
    summary_all: str = Field("", serialization_alias="all")


class BranchDetailDTO(BaseModel):
    """지점 상세 분석 DTO"""

    branch_id: int
    branch_name: str
    location: str
    review_count: int
    tags: list[TagSentimentCountDTO]
    summaries: SummariesOutputDTO
    reviews: list[ReviewOutputDTO]

    @model_serializer
    def _serialize(self) -> dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "branch_name": self.branch_name,
            "location": self.location,
            "review_count": self.review_count,
            "tags": [t.model_dump() for t in self.tags],
            "summaries": self.summaries.model_dump(by_alias=True),
            "reviews": [r.model_dump() for r in self.reviews],
        }
