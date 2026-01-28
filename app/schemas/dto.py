"""
DTO (Data Transfer Object) 모듈

데이터 전송을 위한 타입 안전한 데이터 클래스들을 정의합니다.
레고 블록처럼 조합하여 사용할 수 있습니다.

구현 일지:
- 2026-01-16: 초기 DTO 클래스 생성 (ReviewDTO, SentimentDTO, SummaryRequestDTO,
              SummaryResponseDTO, PipelineConfigDTO, PipelineResultDTO)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

# ==============================================================================
# Review 관련 DTO
# ==============================================================================


@dataclass
class ReviewDTO:
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

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환"""
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


@dataclass
class ProcessedReviewDTO:
    """
    처리된 리뷰 DTO

    키워드 추출 및 감정 분석이 완료된 리뷰입니다.
    """

    review: ReviewDTO
    keywords: list[str] = field(default_factory=list)
    sentiment: Literal["positive", "neutral", "negative"] = "neutral"
    sentiment_score: float = 0.5
    is_negative_filtered: bool = False

    @property
    def branch_id(self) -> int:
        return self.review.branch_id

    @property
    def content(self) -> str:
        return self.review.content

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.review.to_dict(),
            "keywords": self.keywords,
            "sentiment": self.sentiment,
            "sentiment_score": self.sentiment_score,
            "is_negative_filtered": self.is_negative_filtered,
        }


@dataclass
class BranchKeywordsDTO:
    """
    지점별 키워드 집계 DTO
    """

    branch_id: int
    branch_name: str = ""
    keywords: list[str] = field(default_factory=list)
    review_count: int = 0
    keyword_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "branch_name": self.branch_name,
            "keywords": self.keywords,
            "review_count": self.review_count,
            "keyword_counts": self.keyword_counts,
        }


@dataclass
class IncrementalStatsDTO:
    """
    증분 파이프라인 통계 DTO
    """

    total: int = 0
    filtered: int = 0
    processed: int = 0
    positive: int = 0
    negative: int = 0
    neutral: int = 0
    keywords_extracted: int = 0
    branches_updated: set[int] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "filtered": self.filtered,
            "processed": self.processed,
            "positive": self.positive,
            "negative": self.negative,
            "neutral": self.neutral,
            "keywords_extracted": self.keywords_extracted,
            "branches_updated": list(self.branches_updated),
        }


# ==============================================================================
# Sentiment (감정분석) 관련 DTO
# ==============================================================================


@dataclass
class SentimentDTO:
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
        return self.sentiment == "positive" or self.score >= 0.45

    @property
    def is_confident(self) -> bool:
        """신뢰도 높은 결과인지"""
        return self.score >= 0.7 or self.score <= 0.3

    def to_dict(self) -> dict[str, Any]:
        return {
            "sentiment": self.sentiment,
            "score": self.score,
            "method": self.method,
            "confidence": self.confidence,
        }


# ==============================================================================
# Summary (요약) 관련 DTO
# ==============================================================================


@dataclass
class SummaryRequestDTO:
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


@dataclass
class SummaryResponseDTO:
    """
    LLM 요약 응답 DTO

    생성된 요약과 메타데이터를 담습니다.
    """

    branch_id: int
    summary: str
    model: str
    tokens_used: int = 0
    is_valid: bool = True
    validation_errors: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
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


@dataclass
class PipelineConfigDTO:
    """
    파이프라인 설정 DTO

    파이프라인 실행에 필요한 모든 설정을 담습니다.
    기본값이 모두 설정되어 있어 그대로 사용 가능합니다.

    Example:
        >>> config = PipelineConfigDTO()  # 기본값 사용
        >>> config = PipelineConfigDTO(min_reviews=50)  # 커스텀
    """

    # 필터링 설정
    min_reviews: int = 30  # 지점당 최소 리뷰 수
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_reviews": self.min_reviews,
            "min_review_length": self.min_review_length,
            "sentiment_threshold": self.sentiment_threshold,
            "confident_high": self.confident_high,
            "confident_low": self.confident_low,
            "use_bert": self.use_bert,
            "top_n_keywords": self.top_n_keywords,
            "use_keyword_weights": self.use_keyword_weights,
            "use_parallel": self.use_parallel,
            "n_jobs": self.n_jobs,
            "llm_provider": self.llm_provider,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }


@dataclass
class PipelineStepResultDTO:
    """
    파이프라인 단일 스텝 결과 DTO
    """

    step_name: str
    success: bool
    input_count: int
    output_count: int
    duration_seconds: float = 0.0
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_name": self.step_name,
            "success": self.success,
            "input_count": self.input_count,
            "output_count": self.output_count,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
        }


@dataclass
class PipelineResultDTO:
    """
    파이프라인 전체 실행 결과 DTO

    모든 스텝의 결과와 통계를 담습니다.
    """

    success: bool
    total_reviews: int
    processed_reviews: int
    total_branches: int
    summaries_generated: int
    steps: list[PipelineStepResultDTO] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    error_message: str | None = None
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None

    def add_step(self, step: PipelineStepResultDTO):
        """스텝 결과 추가"""
        self.steps.append(step)

    @property
    def failed_steps(self) -> list[str]:
        """실패한 스텝 이름 목록"""
        return [s.step_name for s in self.steps if not s.success]

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "total_reviews": self.total_reviews,
            "processed_reviews": self.processed_reviews,
            "total_branches": self.total_branches,
            "summaries_generated": self.summaries_generated,
            "steps": [s.to_dict() for s in self.steps],
            "total_duration_seconds": self.total_duration_seconds,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


# ==============================================================================
# Summary (요약) Service DTO
# ==============================================================================


@dataclass
class SummaryStatsDTO:
    """
    요약 통계 DTO

    전체 지점 요약 통계를 담습니다.
    """

    total: int
    draft: int
    approved: int
    published: int
    total_reviews: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "draft": self.draft,
            "approved": self.approved,
            "published": self.published,
            "total_reviews": self.total_reviews,
        }


@dataclass
class RegionStatsDTO:
    """
    지역별 통계 DTO
    """

    region: str
    count: int
    avg_rating: float
    total_reviews: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "region": self.region,
            "count": self.count,
            "avg_rating": self.avg_rating,
            "total_reviews": self.total_reviews,
        }


@dataclass
class RatingDistributionDTO:
    """평점 분포 DTO"""

    range_4_5_to_5_0: int = 0
    range_4_0_to_4_5: int = 0
    range_3_5_to_4_0: int = 0
    range_3_0_to_3_5: int = 0
    range_below_3_0: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "4.5-5.0": self.range_4_5_to_5_0,
            "4.0-4.5": self.range_4_0_to_4_5,
            "3.5-4.0": self.range_3_5_to_4_0,
            "3.0-3.5": self.range_3_0_to_3_5,
            "<3.0": self.range_below_3_0,
        }


@dataclass
class RatingStatsDTO:
    """
    평점 분포 통계 DTO
    """

    min: float
    max: float
    avg: float
    total: int
    distribution: RatingDistributionDTO

    def to_dict(self) -> dict[str, Any]:
        return {
            "min": self.min,
            "max": self.max,
            "avg": self.avg,
            "total": self.total,
            "distribution": self.distribution.to_dict(),
        }


@dataclass
class SummaryWithTagsDTO:
    """
    요약 + 태그 조합 DTO
    """

    summary: dict[str, Any] | None
    tags: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "tags": self.tags,
        }


@dataclass
class PendingSummaryResultDTO:
    """
    대기 중인 요약 적용/취소 결과 DTO
    """

    period: str
    applied: str | None = None
    discarded: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {"period": self.period}
        if self.applied is not None:
            result["applied"] = self.applied
        if self.discarded is not None:
            result["discarded"] = self.discarded
        return result


@dataclass
class TagSentimentCountDTO:
    """태그별 감정 카운트 DTO"""

    name: str
    total: int
    positive: int
    negative: int
    neutral: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "total": self.total,
            "positive": self.positive,
            "negative": self.negative,
        }


@dataclass
class ReviewOutputDTO:
    """리뷰 출력 DTO"""

    id: str | None
    date: datetime | str | None
    content: str
    keywords: list[str]
    tag_sentiments: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "date": (
                self.date.isoformat() if isinstance(self.date, datetime) else self.date
            ),
            "content": self.content,
            "keywords": self.keywords,
            "tag_sentiments": self.tag_sentiments,
        }


@dataclass
class SummariesOutputDTO:
    """기간별 요약 출력 DTO"""

    summary_1m: str = ""
    summary_3m: str = ""
    summary_6m: str = ""
    summary_1y: str = ""
    summary_all: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "1m": self.summary_1m,
            "3m": self.summary_3m,
            "6m": self.summary_6m,
            "1y": self.summary_1y,
            "all": self.summary_all,
        }


@dataclass
class BranchDetailDTO:
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "branch_name": self.branch_name,
            "location": self.location,
            "review_count": self.review_count,
            "tags": [t.to_dict() for t in self.tags],
            "summaries": self.summaries.to_dict(),
            "reviews": [r.to_dict() for r in self.reviews],
        }


@dataclass
class BranchReviewsDTO:
    """
    지점별 리뷰 목록 DTO
    """

    reviews: list[dict[str, Any]]
    total: int
    car_models: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reviews": self.reviews,
            "total": self.total,
            "car_models": self.car_models,
        }


# ==============================================================================
# Tag (태그) Service DTO
# ==============================================================================


@dataclass
class KeywordSentimentDTO:
    """키워드 감정 분석 결과 DTO"""

    keyword: str
    sentiment: str

    def to_dict(self) -> dict[str, str]:
        return {
            "keyword": self.keyword,
            "sentiment": self.sentiment,
        }


@dataclass
class TagGroupDTO:
    """태그 그룹 DTO"""

    positive: list[str] = field(default_factory=list)
    negative: list[str] = field(default_factory=list)
    neutral: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "positive": self.positive,
            "negative": self.negative,
            "neutral": self.neutral,
        }


@dataclass
class TagAnalysisResultDTO:
    """
    태그 분석 결과 DTO
    """

    keywords: list[KeywordSentimentDTO]
    tag_groups: dict[str, TagGroupDTO]

    def to_dict(self) -> dict[str, Any]:
        return {
            "keywords": [k.to_dict() for k in self.keywords],
            "tag_groups": {
                name: group.to_dict() for name, group in self.tag_groups.items()
            },
        }


# ==============================================================================
# Sentiment (감정분석) Service DTO
# ==============================================================================


@dataclass
class SentimentStatsDTO:
    """
    감정 통계 DTO
    """

    positive: int
    negative: int
    neutral: int
    total: int
    positive_ratio: float
    negative_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "positive": self.positive,
            "negative": self.negative,
            "neutral": self.neutral,
            "total": self.total,
            "positive_ratio": self.positive_ratio,
            "negative_ratio": self.negative_ratio,
        }


@dataclass
class ReviewSearchResultDTO:
    """
    리뷰 검색 결과 DTO
    """

    reviews: list[dict[str, Any]]
    total: int
    stats: SentimentStatsDTO | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "reviews": self.reviews,
            "total": self.total,
        }
        if self.stats:
            result["stats"] = self.stats.to_dict()
        return result


@dataclass
class CleanupResultDTO:
    """
    리뷰 정리 결과 DTO
    """

    old_deleted: int
    excess_deleted: int
    total: int

    def to_dict(self) -> dict[str, int]:
        return {
            "old_deleted": self.old_deleted,
            "excess_deleted": self.excess_deleted,
            "total": self.total,
        }


# ==============================================================================
# Car Model (차량별 태그) DTO
# ==============================================================================


@dataclass
class CarModelTagDTO:
    """차량별 태그 감정 통계 DTO"""

    name: str
    positive: int = 0
    negative: int = 0
    neutral: int = 0
    total: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "positive": self.positive,
            "negative": self.negative,
            "neutral": self.neutral,
            "total": self.total,
        }


@dataclass
class CarModelDTO:
    """차량 모델별 태그 분석 DTO"""

    name: str
    review_count: int = 0
    tags: list[CarModelTagDTO] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "review_count": self.review_count,
            "tags": [t.to_dict() for t in self.tags],
        }


@dataclass
class BranchCarModelsDTO:
    """지점별 차량 모델 태그 분석 DTO"""

    branch_id: int
    car_models: list[CarModelDTO] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "branch_id": self.branch_id,
            "car_models": [cm.to_dict() for cm in self.car_models],
        }
        if self.error:
            result["error"] = self.error
        return result


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
    # Tag Service
    "KeywordSentimentDTO",
    "TagGroupDTO",
    "TagAnalysisResultDTO",
    # Sentiment Service
    "SentimentStatsDTO",
    "ReviewSearchResultDTO",
    "CleanupResultDTO",
    # Car Model
    "CarModelTagDTO",
    "CarModelDTO",
    "BranchCarModelsDTO",
]
