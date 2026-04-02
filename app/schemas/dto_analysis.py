"""Analysis / CarModel 관련 DTO"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_serializer

from core.constants import NEGATIVE_RATING_THRESHOLD


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


class BranchOptionDTO(BaseModel):
    """지점 옵션 DTO (필터 드롭다운용)"""

    branch_id: int
    branch_name: str
    company_name: str = ""
    region: str = ""


class FilterOptionsDTO(BaseModel):
    """필터 옵션 DTO (계층형 필터 지원)"""

    regions: list[str] = Field(default_factory=list)
    region_groups: dict[str, list[str]] = Field(default_factory=dict)
    companies: list[str] = Field(default_factory=list)
    branches: list[BranchOptionDTO] = Field(default_factory=list)


class AnalysisReviewDTO(BaseModel):
    """분석 페이지용 리뷰 DTO"""

    id: int | None
    review_id: int | None
    reservation_id: str | None = None
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

        db_sentiment = row.get("sentiment")
        if db_sentiment in ("positive", "negative", "neutral"):
            final_sentiment = db_sentiment
        else:
            final_sentiment = cls._calculate_sentiment(
                rating_service, rating_car, rating_convenience, db_sentiment
            )

        return cls(
            id=row.get("id"),
            review_id=row.get("review_id"),
            reservation_id=row.get("reservation_id"),
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
        """평점 + 내용 분석을 결합한 최종 감정 판단"""
        ratings = [r for r in [rating_service, rating_car, rating_convenience] if r is not None]
        is_any_rating_low = any(r < NEGATIVE_RATING_THRESHOLD for r in ratings) if ratings else False

        is_content_negative = content_sentiment == "negative"

        if is_any_rating_low:
            return "negative"
        elif is_content_negative:
            return "neutral"
        else:
            if content_sentiment:
                return content_sentiment
            if ratings:
                avg = sum(ratings) / len(ratings)
                if avg >= 3.5:
                    return "positive"
                if avg >= 3.0:
                    return "neutral"
                return "negative"
            return "neutral"


class AnalysisReviewListDTO(BaseModel):
    """분석 페이지 리뷰 목록 결과 DTO"""

    reviews: list[AnalysisReviewDTO]
    total: int
