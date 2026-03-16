"""Sentiment 관련 DTO"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, model_serializer


class SentimentDTO(BaseModel):
    """감정 분석 결과 DTO"""

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


class SentimentStatsDTO(BaseModel):
    """감정 통계 DTO"""

    positive: int
    negative: int
    neutral: int
    total: int
    positive_ratio: float
    negative_ratio: float


class ReviewSearchResultDTO(BaseModel):
    """리뷰 검색 결과 DTO"""

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
