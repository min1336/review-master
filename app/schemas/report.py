"""리포트 API 요청/응답 스키마 및 데이터 모델"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, model_validator


# ============================================================
# API 요청 DTO
# ============================================================


class ReportRequest(BaseModel):
    """리포트 생성 요청"""

    start_date: date  # YYYY-MM-DD (Pydantic 자동 파싱)
    end_date: date  # YYYY-MM-DD


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

    @model_validator(mode="before")
    @classmethod
    def _migrate_keywords(cls, data):
        """저장된 리포트의 top_keywords → top_tags 하위호환"""
        if isinstance(data, dict) and "top_keywords" in data and "top_tags" not in data:
            data["top_tags"] = data.pop("top_keywords")
        return data
