"""
DTO (Data Transfer Object) 모듈

데이터 전송을 위한 타입 안전한 데이터 클래스들을 정의합니다.
레고 블록처럼 조합하여 사용할 수 있습니다.

구현 일지:
- 2026-01-16: 초기 DTO 클래스 생성 (ReviewDTO, SentimentDTO, SummaryRequestDTO,
              SummaryResponseDTO, PipelineConfigDTO, PipelineResultDTO)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from core.constants import NEGATIVE_RATING_THRESHOLD
from core.timezone import utc_now

# ==============================================================================
# Review 관련 DTO
# ==============================================================================


class ReviewDTO(BaseModel):
    """
    리뷰 원본 데이터 전송 객체

    DB에서 로드한 리뷰 데이터를 타입 안전하게 전달합니다.

    Example:
        >>> review = ReviewDTO(
        ...     id=1,
        ...     branch_id=101,
        ...     content="서비스가 정말 좋았습니다!"
        ... )
        >>> print(review.content)
        서비스가 정말 좋았습니다!
    """

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
    """
    처리된 리뷰 DTO

    키워드 추출 및 감정 분석이 완료된 리뷰입니다.
    """

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
    """
    지점별 키워드 집계 DTO
    """

    branch_id: int
    branch_name: str = ""
    keywords: list[str] = Field(default_factory=list)
    review_count: int = 0
    keyword_counts: dict[str, int] = Field(default_factory=dict)


class IncrementalStatsDTO(BaseModel):
    """
    증분 파이프라인 통계 DTO
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    total: int = 0
    filtered: int = 0
    processed: int = 0
    positive: int = 0
    negative: int = 0
    neutral: int = 0
    keywords_extracted: int = 0
    branches_updated: list[int] = Field(default_factory=list)


# ==============================================================================
# Sentiment (감정분석) 관련 DTO
# ==============================================================================


class SentimentDTO(BaseModel):
    """
    감정 분석 결과 DTO

    기존 SentimentResult와 호환되면서 추가 메타데이터를 포함합니다.

    Attributes:
        sentiment: 감정 분류 ('positive', 'neutral', 'negative')
        score: 감정 점수 (0.0 ~ 1.0)
        method: 분석 방법 ('lexicon', 'bert', 'hybrid')
        confidence: 신뢰도 (선택)
    """

    sentiment: Literal["positive", "neutral", "negative"]
    score: float  # 0.0 ~ 1.0
    method: str  # 'lexicon', 'bert', 'hybrid'
    confidence: float | None = None

    @property
    def is_positive(self) -> bool:
        return self.sentiment == "positive" or (self.sentiment != "negative" and self.score >= 0.45)

    @property
    def is_confident(self) -> bool:
        """신뢰도 높은 결과인지"""
        return self.score >= 0.7 or self.score <= 0.3


# ==============================================================================
# Summary (요약) 관련 DTO
# ==============================================================================


class SummaryRequestDTO(BaseModel):
    """
    LLM 요약 요청 DTO

    LLM에 요약 생성을 요청할 때 필요한 모든 정보를 담습니다.

    Example:
        >>> request = SummaryRequestDTO(
        ...     branch_id=101,
        ...     branch_name="강남점",
        ...     keywords=["친절", "서비스", "깨끗"],
        ...     representative_reviews=["정말 좋았어요", "추천합니다"],
        ...     review_count=150
        ... )
    """

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
    """
    LLM 요약 응답 DTO

    생성된 요약과 메타데이터를 담습니다.
    """

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


# ==============================================================================
# Pipeline 설정 및 결과 DTO
# ==============================================================================


class PipelineConfigDTO(BaseModel):
    """
    파이프라인 설정 DTO

    파이프라인 실행에 필요한 모든 설정을 담습니다.
    기본값이 모두 설정되어 있어 그대로 사용 가능합니다.

    Example:
        >>> config = PipelineConfigDTO()  # 기본값 사용
        >>> config = PipelineConfigDTO(min_reviews=50)  # 커스텀
    """

    # 필터링 설정
    min_review_length: int = 5  # 최소 리뷰 글자 수

    # 감정분석 설정
    sentiment_threshold: float = 0.45  # 긍정 판정 기준
    confident_high: float = 0.7  # 확실한 긍정
    confident_low: float = 0.3  # 확실한 부정
    use_bert: bool = True  # BERT 사용 여부

    # 키워드 설정
    top_n_keywords: int = 10  # 상위 N개 키워드
    use_keyword_weights: bool = True  # 가중치 사용 여부

    # 병렬 처리 설정
    use_parallel: bool = True
    n_jobs: int = -1  # -1 = 모든 CPU 사용

    # LLM 설정
    llm_provider: str = "openai"  # "openai"
    max_tokens: int = 300
    temperature: float = 0.7


class PipelineStepResultDTO(BaseModel):
    """
    파이프라인 단일 스텝 결과 DTO
    """

    step_name: str
    success: bool
    input_count: int
    output_count: int
    duration_seconds: float = 0.0
    error_message: str | None = None


class PipelineResultDTO(BaseModel):
    """
    파이프라인 전체 실행 결과 DTO

    모든 스텝의 결과와 통계를 담습니다.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool
    total_reviews: int
    processed_reviews: int
    total_branches: int
    summaries_generated: int
    steps: list[PipelineStepResultDTO] = Field(default_factory=list)
    total_duration_seconds: float = 0.0
    error_message: str | None = None
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None

    def add_step(self, step: PipelineStepResultDTO):
        """스텝 결과 추가"""
        self.steps.append(step)

    @property
    def failed_steps(self) -> list[str]:
        """실패한 스텝 이름 목록"""
        return [s.step_name for s in self.steps if not s.success]

    @model_serializer
    def _serialize(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "total_reviews": self.total_reviews,
            "processed_reviews": self.processed_reviews,
            "total_branches": self.total_branches,
            "summaries_generated": self.summaries_generated,
            "steps": [s.model_dump() for s in self.steps],
            "total_duration_seconds": self.total_duration_seconds,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


# ==============================================================================
# Summary (요약) Service DTO
# ==============================================================================


class SummaryStatsDTO(BaseModel):
    """
    요약 통계 DTO

    전체 지점 요약 통계를 담습니다.
    """

    total: int
    total_reviews: int


class RegionStatsDTO(BaseModel):
    """
    지역별 통계 DTO
    """

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
    """
    평점 분포 통계 DTO
    """

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
    """
    요약 + 태그 조합 DTO
    """

    summary: dict[str, Any] | None
    tags: list[dict[str, Any]]


class PendingSummaryResultDTO(BaseModel):
    """
    대기 중인 요약 적용/취소 결과 DTO
    """

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
    """
    지점 상세 분석 DTO
    """

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


class BranchReviewsDTO(BaseModel):
    """
    지점별 리뷰 목록 DTO
    """

    reviews: list[dict[str, Any]]
    total: int
    car_models: list[str] = Field(default_factory=list)


# ==============================================================================
# Tag (태그) Service DTO
# ==============================================================================


# ==============================================================================
# Sentiment (감정분석) Service DTO
# ==============================================================================


class SentimentStatsDTO(BaseModel):
    """
    감정 통계 DTO
    """

    positive: int
    negative: int
    neutral: int
    total: int
    positive_ratio: float
    negative_ratio: float


class ReviewSearchResultDTO(BaseModel):
    """
    리뷰 검색 결과 DTO
    """

    reviews: list[dict[str, Any]]
    total: int
    stats: SentimentStatsDTO | None = None

    @model_serializer
    def _serialize(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "reviews": self.reviews,
            "total": self.total,
        }
        if self.stats:
            result["stats"] = self.stats.model_dump()
        return result


class CleanupResultDTO(BaseModel):
    """
    리뷰 정리 결과 DTO
    """

    old_deleted: int
    excess_deleted: int
    total: int


# ==============================================================================
# Car Model (차량별 태그) DTO
# ==============================================================================


class CarModelTagDTO(BaseModel):
    """차량별 태그 감정 통계 DTO"""

    name: str
    positive: int = 0
    negative: int = 0
    neutral: int = 0
    total: int = 0


class CarModelDTO(BaseModel):
    """차량 모델별 태그 분석 DTO"""

    name: str
    review_count: int = 0
    tags: list[CarModelTagDTO] = Field(default_factory=list)


class BranchCarModelsDTO(BaseModel):
    """지점별 차량 모델 태그 분석 DTO"""

    branch_id: int
    car_models: list[CarModelDTO] = Field(default_factory=list)
    error: str | None = None

    @model_serializer
    def _serialize(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "branch_id": self.branch_id,
            "car_models": [cm.model_dump() for cm in self.car_models],
        }
        if self.error:
            result["error"] = self.error
        return result


# ==============================================================================
# Analysis (분석 페이지) DTO
# ==============================================================================


class BranchOptionDTO(BaseModel):
    """
    지점 옵션 DTO

    필터 드롭다운에서 사용하는 지점 정보입니다.
    """

    branch_id: int
    branch_name: str
    company_name: str = ""
    region: str = ""


class FilterOptionsDTO(BaseModel):
    """
    필터 옵션 DTO (계층형 필터 지원)

    분석 페이지의 필터 드롭다운에 사용되는 옵션들을 담습니다.
    branches에 region, company_name이 포함되어 계층형 필터링 가능.
    """

    regions: list[str] = Field(default_factory=list)
    region_groups: dict[str, list[str]] = Field(default_factory=dict)
    companies: list[str] = Field(default_factory=list)
    branches: list[BranchOptionDTO] = Field(default_factory=list)


class AnalysisReviewDTO(BaseModel):
    """
    분석 페이지용 리뷰 DTO
    """

    id: int | None
    review_id: int | None
    branch_id: int | None
    branch_name: str
    company_name: str
    content: str
    sentiment: str | None
    review_date: str | None
    rating_service: float | None
    rating_car: float | None
    rating_convenience: float | None
    car_model: str | None = None
    is_new: bool = False

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "AnalysisReviewDTO":
        """DB row에서 DTO 생성"""
        review_date = row.get("review_date")
        if isinstance(review_date, datetime):
            review_date = review_date.isoformat()

        # 평점 추출 (Athena는 문자열 반환 → float 변환)
        def _safe_float(val: Any) -> float | None:
            if val is None:
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        rating_service = _safe_float(row.get("rating_service"))
        rating_car = _safe_float(row.get("rating_car"))
        rating_convenience = _safe_float(row.get("rating_convenience"))

        # 감정: DB에 파이프라인이 계산한 값이 있으면 그대로 사용
        db_sentiment = row.get("sentiment")
        if db_sentiment in ("positive", "negative", "neutral"):
            final_sentiment = db_sentiment
        else:
            # DB 감정 없는 경우(Athena 등) → 평점 기반 fallback
            final_sentiment = cls._calculate_sentiment(
                rating_service, rating_car, rating_convenience, db_sentiment
            )

        return cls(
            id=row.get("id"),
            review_id=row.get("review_id"),
            branch_id=row.get("branch_id"),
            branch_name=row.get("branch_name") or "",
            company_name=row.get("company_name") or "",
            content=row.get("content") or "",
            sentiment=final_sentiment,
            review_date=review_date,
            rating_service=rating_service,
            rating_car=rating_car,
            rating_convenience=rating_convenience,
            car_model=row.get("car_model"),
            is_new=row.get("is_new", False),
        )

    @staticmethod
    def _calculate_sentiment(
        rating_service: float | None,
        rating_car: float | None,
        rating_convenience: float | None,
        content_sentiment: str | None,
    ) -> str:
        """
        평점 + 내용 분석을 결합한 최종 감정 판단

        규칙:
        1. 3가지 평점 중 1개라도 낮으면(3점 이하) → 부정
        2. 내용 분석이 부정인데 평점이 모두 높으면 → 중립
        3. 평점 높고 내용도 긍정/중립 → 기존 감정 유지
        """
        # 평점 검사: 유효한 평점만 확인 (3.0 미만이면 부정)
        ratings = [r for r in [rating_service, rating_car, rating_convenience] if r is not None]
        is_any_rating_low = any(r < NEGATIVE_RATING_THRESHOLD for r in ratings) if ratings else False

        # 내용 기반 감정 (기본값: neutral)
        is_content_negative = content_sentiment == "negative"

        # 규칙 적용
        if is_any_rating_low:
            # 평점이 하나라도 낮으면 무조건 부정
            return "negative"
        elif is_content_negative:
            # 평점은 다 높은데 내용이 부정이면 → 중립
            return "neutral"
        else:
            # 평점 높고 내용도 부정 아님 → 기존 감정 유지
            if content_sentiment:
                return content_sentiment
            # DB에 sentiment 없는 경우: 평점 기반 판단
            if ratings:
                avg = sum(ratings) / len(ratings)
                if avg >= 3.5:
                    return "positive"
                if avg >= 3.0:
                    return "neutral"
                return "negative"
            return "neutral"


class AnalysisReviewListDTO(BaseModel):
    """
    분석 페이지 리뷰 목록 결과 DTO
    """

    reviews: list[AnalysisReviewDTO]
    total: int


# ==============================================================================
# 내보내기
# ==============================================================================

__all__ = [
    # Review
    "ReviewDTO",
    "ProcessedReviewDTO",
    "BranchKeywordsDTO",
    "IncrementalStatsDTO",
    # Sentiment
    "SentimentDTO",
    # Summary Request/Response
    "SummaryRequestDTO",
    "SummaryResponseDTO",
    # Pipeline
    "PipelineConfigDTO",
    "PipelineStepResultDTO",
    "PipelineResultDTO",
    # Summary Service
    "SummaryStatsDTO",
    "RegionStatsDTO",
    "RatingDistributionDTO",
    "RatingStatsDTO",
    "SummaryWithTagsDTO",
    "PendingSummaryResultDTO",
    "TagSentimentCountDTO",
    "ReviewOutputDTO",
    "SummariesOutputDTO",
    "BranchDetailDTO",
    "BranchReviewsDTO",
    # Sentiment Service
    "SentimentStatsDTO",
    "ReviewSearchResultDTO",
    "CleanupResultDTO",
    # Car Model
    "CarModelTagDTO",
    "CarModelDTO",
    "BranchCarModelsDTO",
    # Analysis
    "BranchOptionDTO",
    "FilterOptionsDTO",
    "AnalysisReviewDTO",
    "AnalysisReviewListDTO",
]
