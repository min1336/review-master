"""Review 관련 DTO"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer


class ReviewDTO(BaseModel):
    """리뷰 원본 데이터 전송 객체"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: int
    branch_id: int
    content: str
    branch_name: str = ""
    rating: float | None = None
    created_at: datetime | None = None
    like_count: int = 0
    is_blind: bool = False
    car_model: str = ""
    company_name: str = ""
    status: str = "normal"

    def is_valid(self) -> bool:
        """리뷰가 유효한지 검사"""
        return (
            self.content is not None
            and len(self.content.strip()) >= 5
            and not self.is_blind
            and self.status not in ["블라인드", "삭제", "blind", "deleted"]
        )

    @model_serializer
    def _serialize(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "branch_id": self.branch_id,
            "branch_name": self.branch_name,
            "content": self.content,
            "rating": self.rating,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "like_count": self.like_count,
            "is_blind": self.is_blind,
            "car_model": self.car_model,
            "company_name": self.company_name,
            "status": self.status,
        }

    @classmethod
    def from_athena_row(cls, row: dict[str, Any]) -> "ReviewDTO":
        """Athena 쿼리 결과에서 ReviewDTO 생성 (모든 값이 문자열)"""
        created_at = None
        review_date = row.get("review_date")
        if review_date:
            try:
                created_at = datetime.fromisoformat(str(review_date).replace("Z", "+00:00"))
            except ValueError:
                created_at = None

        def safe_int(val, default=0):
            try:
                return int(val) if val else default
            except (ValueError, TypeError):
                return default

        def safe_float(val, default=None):
            try:
                return float(val) if val else default
            except (ValueError, TypeError):
                return default

        return cls(
            id=safe_int(row.get("review_id")),
            branch_id=safe_int(row.get("branch_id")),
            content=(row.get("content") or "").strip(),
            branch_name=row.get("branch_name") or "",
            rating=safe_float(row.get("rating_service")),
            created_at=created_at,
            like_count=safe_int(row.get("helpful_count")),
            is_blind=False,
            car_model=row.get("car_type") or "",
            company_name=row.get("company_name") or "",
            status=row.get("status") or "1",
        )

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "ReviewDTO":
        """DB row에서 ReviewDTO 생성"""
        created_at = row.get("review_date") or row.get("created_at")
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                created_at = None

        return cls(
            id=row.get("id") or row.get("review_id") or 0,
            branch_id=row.get("branch_id") or 0,
            content=row.get("content") or "",
            branch_name=row.get("branch_name") or "",
            rating=row.get("rating_service") or row.get("rating") or None,
            created_at=created_at,
            like_count=row.get("helpful_count") or row.get("like_count") or 0,
            is_blind=row.get("is_blind", False),
            car_model=row.get("car_model") or "",
            company_name=row.get("company_name") or "",
            status=row.get("status") or "normal",
        )


class ProcessedReviewDTO(BaseModel):
    """처리된 리뷰 DTO (키워드 추출 및 감정 분석 완료)"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    review: ReviewDTO
    keywords: list[str] = Field(default_factory=list)
    sentiment: Literal["positive", "neutral", "negative"] = "neutral"
    sentiment_score: float = 0.5
    is_negative_filtered: bool = False
    tag_sentiments: dict[str, dict[str, list[str]]] = Field(default_factory=dict)
    # 구조: {"직원친절": {"positive": ["친절", "좋은"], "negative": [], "neutral": []}, ...}
    rating_car: float | None = None
    rating_convenience: float | None = None

    @property
    def branch_id(self) -> int:
        return self.review.branch_id

    @property
    def content(self) -> str:
        return self.review.content

    @model_serializer
    def _serialize(self) -> dict[str, Any]:
        return {
            **self.review.model_dump(),
            "keywords": self.keywords,
            "sentiment": self.sentiment,
            "sentiment_score": self.sentiment_score,
            "is_negative_filtered": self.is_negative_filtered,
        }


class BranchKeywordsDTO(BaseModel):
    """지점별 키워드 집계 DTO"""

    branch_id: int
    branch_name: str = ""
    keywords: list[str] = Field(default_factory=list)
    review_count: int = 0
    keyword_counts: dict[str, int] = Field(default_factory=dict)


class IncrementalStatsDTO(BaseModel):
    """증분 파이프라인 통계 DTO"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    total: int = 0
    filtered: int = 0
    processed: int = 0
    positive: int = 0
    negative: int = 0
    neutral: int = 0
    keywords_extracted: int = 0
    branches_updated: list[int] = Field(default_factory=list)


class BranchReviewsDTO(BaseModel):
    """지점별 리뷰 목록 DTO"""

    reviews: list[dict[str, Any]]
    total: int
    car_models: list[str] = Field(default_factory=list)


class CleanupResultDTO(BaseModel):
    """리뷰 정리 결과 DTO"""

    old_deleted: int
    excess_deleted: int
    total: int
