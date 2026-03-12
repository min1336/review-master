"""리포트 API 요청/응답 스키마 및 데이터 모델"""

from __future__ import annotations

from datetime import date

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ============================================================
# 리포트 커스텀 설정 DTO
# ============================================================


class ReportOutputConfig(BaseModel):
    """출력 섹션 설정"""
    include_period_summary: bool = True
    include_affiliate_eval: bool = True
    include_vehicle_eval: bool = True
    include_trend_comparison: bool = False
    include_benchmark: bool = True
    include_priority_actions: bool = False
    summary_max_length: int = Field(300, ge=150, le=1000)
    eval_max_length: int = Field(150, ge=100, le=400)


class ReportDataConfig(BaseModel):
    """데이터 포함 범위"""
    include_tags: bool = True
    include_vehicles: bool = True
    include_sample_reviews: bool = True
    sample_review_count: int = Field(10, ge=5, le=20)


VALID_FOCUS_AREAS = [
    "직원친절", "외관", "가격", "청결",
    "사고 처리", "주유비", "배달/배차", "반납/픽업", "위치/접근성",
]


class ReportPromptConfig(BaseModel):
    """프롬프트 커스터마이징"""
    custom_instruction: str = Field("", max_length=500)
    analysis_perspective: Literal[
        "operational", "marketing", "executive",
        "customer_service", "investor", "comparative",
    ] = "operational"
    tone: Literal[
        "analytical", "friendly", "formal",
        "concise", "data_driven", "narrative",
    ] = "analytical"
    detail_level: Literal["brief", "standard", "detailed"] = "standard"
    focus_areas: list[str] = Field(default_factory=list)
    temperature: float = Field(0.5, ge=0.0, le=1.0)
    preset_id: int | None = None

    @field_validator("custom_instruction")
    @classmethod
    def sanitize_instruction(cls, v: str) -> str:
        """제어 문자 제거"""
        return v.strip()

    @field_validator("focus_areas")
    @classmethod
    def filter_focus_areas(cls, v: list[str]) -> list[str]:
        """유효한 카테고리만 허용"""
        return [area for area in v if area in VALID_FOCUS_AREAS]


class ResolvedReportConfig(BaseModel):
    """API 진입점에서 1회 생성되는 통합 설정 (전 계층에서 사용)"""
    output: ReportOutputConfig = Field(default_factory=ReportOutputConfig)
    data: ReportDataConfig = Field(default_factory=ReportDataConfig)
    prompt: ReportPromptConfig = Field(default_factory=ReportPromptConfig)

    @model_validator(mode="after")
    def enforce_dependencies(self):
        """불가능 조합 자동 보정: 평가 섹션 ON이면 해당 데이터도 ON"""
        if self.output.include_affiliate_eval and not self.data.include_tags:
            self.data.include_tags = True
        if self.output.include_vehicle_eval and not self.data.include_vehicles:
            self.data.include_vehicles = True
        return self


# ============================================================
# API 요청 DTO
# ============================================================


# ============================================================
# 프리셋 DTO
# ============================================================


class PromptPresetCreate(BaseModel):
    """프리셋 생성 요청"""
    name: str = Field(..., min_length=1, max_length=100)
    description: str = ""
    branch_type: Literal["airport", "tourist", "city"] | None = None
    analysis_perspective: Literal[
        "operational", "marketing", "executive",
        "customer_service", "investor", "comparative",
    ] = "operational"
    tone: Literal[
        "analytical", "friendly", "formal",
        "concise", "data_driven", "narrative",
    ] = "analytical"
    detail_level: Literal["brief", "standard", "detailed"] = "standard"
    focus_areas: list[str] = Field(default_factory=list)
    custom_instruction: str = Field("", max_length=500)
    temperature: float = Field(0.5, ge=0.0, le=1.0)
    summary_max_length: int = Field(300, ge=150, le=1000)
    eval_max_length: int = Field(150, ge=100, le=400)
    is_default: bool = False
    display_order: int = 0

    @field_validator("focus_areas")
    @classmethod
    def filter_focus_areas(cls, v: list[str]) -> list[str]:
        return [area for area in v if area in VALID_FOCUS_AREAS]


class PromptPresetUpdate(BaseModel):
    """프리셋 수정 요청"""
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    branch_type: Literal["airport", "tourist", "city"] | None = None
    analysis_perspective: Literal[
        "operational", "marketing", "executive",
        "customer_service", "investor", "comparative",
    ] | None = None
    tone: Literal[
        "analytical", "friendly", "formal",
        "concise", "data_driven", "narrative",
    ] | None = None
    detail_level: Literal["brief", "standard", "detailed"] | None = None
    focus_areas: list[str] | None = None
    custom_instruction: str | None = Field(None, max_length=500)
    temperature: float | None = Field(None, ge=0.0, le=1.0)
    summary_max_length: int | None = Field(None, ge=150, le=1000)
    eval_max_length: int | None = Field(None, ge=100, le=400)
    is_default: bool | None = None
    display_order: int | None = None

    @field_validator("focus_areas")
    @classmethod
    def filter_focus_areas(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        return [area for area in v if area in VALID_FOCUS_AREAS]


class PromptPresetResponse(BaseModel):
    """프리셋 응답"""
    id: int
    name: str
    description: str = ""
    branch_type: str | None = None
    analysis_perspective: str = "operational"
    tone: str = "analytical"
    detail_level: str = "standard"
    focus_areas: list[str] = Field(default_factory=list)
    custom_instruction: str = ""
    temperature: float = 0.5
    summary_max_length: int = 300
    eval_max_length: int = 150
    is_default: bool = False
    is_active: bool = True
    display_order: int = 0
    created_at: str | None = None
    updated_at: str | None = None


# ============================================================
# API 요청 DTO
# ============================================================


class ReportRequest(BaseModel):
    """리포트 생성 요청"""

    start_date: date  # YYYY-MM-DD (Pydantic 자동 파싱)
    end_date: date  # YYYY-MM-DD
    output_config: ReportOutputConfig | None = None
    data_config: ReportDataConfig | None = None
    prompt_config: ReportPromptConfig | None = None

    def to_resolved_config(self) -> ResolvedReportConfig:
        """Optional 필드들을 기본값 merge하여 ResolvedReportConfig 생성"""
        return ResolvedReportConfig(
            output=self.output_config or ReportOutputConfig(),
            data=self.data_config or ReportDataConfig(),
            prompt=self.prompt_config or ReportPromptConfig(),
        )


class BatchPdfRequest(BaseModel):
    """일괄 PDF 다운로드 요청"""
    branch_ids: list[int] = Field(..., min_length=1, max_length=5)
    start_date: date
    end_date: date


# ============================================================
# 리포트 데이터 모델
# ============================================================


class TagRankItem(BaseModel):
    """태그 순위 항목"""
    tag_name: str
    category_name: str
    count: int = 0               # 긍정 or 부정 건수
    ratio: int = 0               # 해당 감정 비율 %


class VehicleRankItem(BaseModel):
    """차량 순위 항목"""
    model: str
    count: int = 0               # 총 리뷰 건수
    ratio: int = 0               # 호평 or 불만 비율
    tags: list[str] = []         # ["냄새(85%)", "청결(72%)"] 최대 3개


class AffiliateEvaluation(BaseModel):
    """업체 평가 섹션"""
    top_positive: list[TagRankItem] = []   # Top 5 긍정 태그
    top_negative: list[TagRankItem] = []   # Top 5 부정 태그
    ai_text: str = ""                       # AI 평가 텍스트 (150-250자)


class VehicleEvaluation(BaseModel):
    """차량 평가 섹션"""
    top_liked: list[VehicleRankItem] = []   # 호평 Top 5 차량
    top_disliked: list[VehicleRankItem] = [] # 불만 Top 5 차량
    ai_text: str = ""                        # AI 평가 텍스트 (150-250자)


class VehicleAnalysis(BaseModel):
    """차량별 분석"""
    model: str
    count: int = 0
    avg_sentiment: float = 0.0
    top_praise: str = ""
    top_issue: str = ""
    like_ratio: int = 0  # 호평 비율 (0-100)
    dislike_ratio: int = 0  # 불평 비율 (0-100)


class StrengthItem(BaseModel):
    """현상유지/보완필요 구조화 항목"""
    category_name: str
    ratio: int = 0  # 긍정률 or 부정률

class TopTagItem(BaseModel):
    """Top 태그 구조화 항목"""
    name: str
    count: int = 0
    positive_ratio: int = 0


class TrendItem(BaseModel):
    """카테고리별 트렌드 항목"""
    category_name: str
    current_ratio: int = 0          # 현재 기간 긍정률
    previous_ratio: int = 0         # 이전 기간 긍정률
    change: int = 0                 # 변화량 (현재 - 이전, pp)
    direction: str = "stable"       # "up" / "down" / "stable"


class TrendComparison(BaseModel):
    """트렌드 비교 섹션"""
    previous_period: str = ""               # "2025-10-01 ~ 2025-12-31"
    current_period: str = ""                # "2026-01-01 ~ 2026-03-31"
    previous_total_reviews: int = 0
    current_total_reviews: int = 0
    overall_positive_change: int = 0        # 전체 긍정률 변화 (pp)
    overall_negative_change: int = 0        # 전체 부정률 변화 (pp)
    category_trends: list[TrendItem] = []


class BenchmarkData(BaseModel):
    """벤치마크 비교 섹션"""
    branch_rating: float = 0.0
    regional_avg_rating: float = 0.0
    national_avg_rating: float = 0.0
    regional_rank_pct: int = 0              # 지역 내 상위 N%
    national_rank_pct: int = 0              # 전국 상위 N%
    region_name: str = ""
    total_branches_in_region: int = 0
    total_branches_national: int = 0


class PriorityAction(BaseModel):
    """우선순위 액션 아이템"""
    rank: int = 0
    category_name: str = ""
    tag_name: str = ""
    issue: str = ""
    action: str = ""
    impact: str = "medium"                  # high / medium / low
    effort: str = "low"                     # high / medium / low
    negative_ratio: int = 0
    negative_count: int = 0


class NegativeReviewItem(BaseModel):
    """부정 리뷰 항목"""
    content: str = ""
    rating: float = 0.0
    review_date: str = ""
    vehicle_model: str = ""


class TagCoverage(BaseModel):
    """태그 분석 커버리지 (신뢰도 표기용)"""
    tagged_reviews: int = 0      # 태그가 1개 이상 있는 리뷰 수
    total_reviews: int = 0       # 전체 리뷰 수
    ratio: int = 0               # 커버리지 비율 (0-100%)


class ReportData(BaseModel):
    """리포트 전체 데이터"""
    branch_id: int
    branch_name: str
    affiliate_name: str
    period_start: str
    period_end: str
    total_reviews: int = 0
    top_tags: list[str] = []
    period_summary: str = ""
    strengths: list[str] = []       # 현상유지 (잘하고 있는 카테고리)
    improvements: list[str] = []    # 보완필요 (개선이 필요한 카테고리)
    strengths_detail: list[StrengthItem] = []       # 구조화된 현상유지
    improvements_detail: list[StrengthItem] = []    # 구조화된 보완필요
    top_tags_detail: list[TopTagItem] = []           # 구조화된 Top 태그
    vehicle_analysis: list[VehicleAnalysis] = []
    affiliate_evaluation: AffiliateEvaluation | None = None
    vehicle_evaluation: VehicleEvaluation | None = None
    generated_at: str = ""
    tag_coverage: TagCoverage | None = None
    # 신규 인사이트 섹션 (선택적, 하위호환)
    trend_comparison: TrendComparison | None = None
    benchmark: BenchmarkData | None = None
    priority_actions: list[PriorityAction] = []
    negative_reviews: list[NegativeReviewItem] = []

    @model_validator(mode="before")
    @classmethod
    def _migrate_keywords(cls, data):
        """저장된 리포트의 top_keywords → top_tags 하위호환"""
        if isinstance(data, dict) and "top_keywords" in data and "top_tags" not in data:
            data["top_tags"] = data.pop("top_keywords")
        return data
