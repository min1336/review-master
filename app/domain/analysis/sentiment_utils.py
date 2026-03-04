"""
통합 감정 분석 모듈

세 가지 분석 방식을 결합하여 최적의 감정 판단을 수행합니다:
1. Rule-based (ABSA): 빠른 패턴 매칭
2. HybridClassifier: 문맥 고려 분석
3. Rating 통합: 평점과 텍스트 결합 판단
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from core.constants import HIGH_RATING_THRESHOLD, NEGATIVE_RATING_THRESHOLD

SentimentType = Literal["positive", "neutral", "negative"]


@dataclass
class SentimentResult:
    """통합 감정 분석 결과"""

    sentiment: SentimentType
    confidence: float  # 0.0 ~ 1.0
    method: str  # 어떤 방식으로 최종 결정했는지
    details: dict  # 각 방식별 세부 결과


class UnifiedSentimentAnalyzer:
    """
    통합 감정 분석기

    세 가지 분석 방식을 결합하여 가장 정확한 감정 판단을 수행합니다.

    Usage:
        analyzer = UnifiedSentimentAnalyzer()

        # 텍스트만 분석
        result = analyzer.analyze("정말 친절하고 좋았습니다")

        # 텍스트 + 키워드
        result = analyzer.analyze("서비스 최고", keywords=["친절", "청결"])

        # 텍스트 + 키워드 + 평점
        result = analyzer.analyze_with_ratings(
            text="좋았습니다",
            keywords=["친절"],
            rating_service=4.5,
            rating_car=5.0,
            rating_convenience=4.0,
        )
    """

    # 분석 방식별 가중치
    WEIGHT_RULE_BASED = 0.3
    WEIGHT_HYBRID = 0.4

    # 평점 임계값 (core.constants에서 관리)
    LOW_RATING_THRESHOLD = NEGATIVE_RATING_THRESHOLD
    HIGH_RATING_THRESHOLD = HIGH_RATING_THRESHOLD

    def __init__(self, lazy_load: bool = True, hybrid_classifier=None):
        self._absa = None
        self._hybrid = hybrid_classifier
        self._lazy_load = lazy_load

        if not lazy_load:
            self._init_analyzers()

    def _init_analyzers(self):
        """분석기 초기화 (지연 로딩)"""
        if self._absa is None:
            from .absa import RuleBasedABSA

            self._absa = RuleBasedABSA()

        if self._hybrid is None:
            from domain.analysis._singletons import get_hybrid_classifier

            self._hybrid = get_hybrid_classifier()

    def analyze(
        self,
        text: str,
        keywords: list[str] | None = None,
    ) -> SentimentResult:
        """
        텍스트 감정 분석 (평점 없이)

        Args:
            text: 분석할 텍스트
            keywords: 추출된 키워드 (없으면 자동 추출)

        Returns:
            SentimentResult: 분석 결과
        """
        if not text or not text.strip():
            return SentimentResult(
                sentiment="neutral",
                confidence=0.0,
                method="empty",
                details={"reason": "빈 텍스트"},
            )

        self._init_analyzers()

        # 1. Rule-based 분석 (ABSA)
        rule_sentiment, rule_confidence = self._analyze_rule_based(text)

        # 2. Hybrid 분석
        hybrid_result = self._analyze_hybrid(text, keywords)
        hybrid_sentiment = hybrid_result["sentiment"]
        hybrid_confidence = hybrid_result["confidence"]

        # 3. 결과 통합 (가중 평균)
        final_sentiment, final_confidence, method = self._combine_results(
            rule_sentiment=rule_sentiment,
            rule_confidence=rule_confidence,
            hybrid_sentiment=hybrid_sentiment,
            hybrid_confidence=hybrid_confidence,
        )

        return SentimentResult(
            sentiment=final_sentiment,
            confidence=final_confidence,
            method=method,
            details={
                "rule_based": {"sentiment": rule_sentiment, "confidence": rule_confidence},
                "hybrid": {"sentiment": hybrid_sentiment, "confidence": hybrid_confidence},
            },
        )

    def analyze_with_ratings(
        self,
        text: str,
        keywords: list[str] | None = None,
        rating_service: float | None = None,
        rating_car: float | None = None,
        rating_convenience: float | None = None,
    ) -> SentimentResult:
        """
        텍스트 + 평점 통합 감정 분석

        Args:
            text: 분석할 텍스트
            keywords: 추출된 키워드
            rating_service: 서비스 평점 (1~5)
            rating_car: 차량 평점 (1~5)
            rating_convenience: 편의성 평점 (1~5)

        Returns:
            SentimentResult: 분석 결과
        """
        # 텍스트 분석 먼저 수행
        text_result = self.analyze(text, keywords)

        # 평점이 없으면 텍스트 분석 결과만 반환
        ratings = [r for r in [rating_service, rating_car, rating_convenience] if r is not None]
        if not ratings:
            return text_result

        # 평점 기반 감정 계산
        rating_sentiment, rating_confidence = self._analyze_ratings(ratings)

        # 최종 통합 (텍스트 + 평점)
        final_sentiment, final_confidence, method = self._integrate_with_ratings(
            text_sentiment=text_result.sentiment,
            text_confidence=text_result.confidence,
            rating_sentiment=rating_sentiment,
            rating_confidence=rating_confidence,
            ratings=ratings,
        )

        return SentimentResult(
            sentiment=final_sentiment,
            confidence=final_confidence,
            method=method,
            details={
                **text_result.details,
                "ratings": {
                    "sentiment": rating_sentiment,
                    "confidence": rating_confidence,
                    "avg_rating": sum(ratings) / len(ratings),
                },
            },
        )

    def _analyze_rule_based(self, text: str) -> tuple[SentimentType, float]:
        """Rule-based 감정 분석 — ABSA에 위임"""
        return self._absa.determine_text_sentiment(text)

    def _analyze_hybrid(
        self, text: str, keywords: list[str] | None
    ) -> dict:
        """HybridClassifier 분석"""
        result = self._hybrid.get_review_summary(text, keywords)

        overall = result.get("overall_sentiment", "neutral")
        pos_aspects = result.get("positive_aspects", [])
        neg_aspects = result.get("negative_aspects", [])

        # "mixed" 등 비표준 감정값 → 다수결로 해소
        if overall not in ("positive", "negative", "neutral"):
            if len(pos_aspects) > len(neg_aspects):
                overall = "positive"
            elif len(neg_aspects) > len(pos_aspects):
                overall = "negative"
            else:
                overall = "neutral"

        total = len(pos_aspects) + len(neg_aspects)
        if total == 0:
            confidence = 0.5
        else:
            # Laplace smoothing
            if overall == "positive":
                confidence = (len(pos_aspects) + 1) / (total + 2)
            elif overall == "negative":
                confidence = (len(neg_aspects) + 1) / (total + 2)
            else:
                confidence = 0.5

        return {
            "sentiment": overall,
            "confidence": min(0.95, confidence),
            "positive_aspects": pos_aspects,
            "negative_aspects": neg_aspects,
        }

    def _combine_results(
        self,
        rule_sentiment: SentimentType,
        rule_confidence: float,
        hybrid_sentiment: SentimentType,
        hybrid_confidence: float,
    ) -> tuple[SentimentType, float, str]:
        """두 분석 결과 통합"""
        # 두 방식이 일치하면 높은 신뢰도
        if rule_sentiment == hybrid_sentiment:
            combined_confidence = max(rule_confidence, hybrid_confidence)
            return rule_sentiment, combined_confidence, "consensus"

        # 불일치 시: 가중 점수 승자 선택 (신뢰도 감쇄)
        rule_weighted = rule_confidence * self.WEIGHT_RULE_BASED
        hybrid_weighted = hybrid_confidence * self.WEIGHT_HYBRID

        if rule_weighted >= hybrid_weighted:
            return rule_sentiment, rule_confidence * 0.85, "rule_based_override"
        else:
            return hybrid_sentiment, hybrid_confidence * 0.85, "hybrid_override"

    def _analyze_ratings(
        self, ratings: list[float]
    ) -> tuple[SentimentType, float]:
        """평점 기반 감정 분석"""
        avg_rating = sum(ratings) / len(ratings)
        min_rating = min(ratings)

        # 최저 평점이 낮으면 부정 (3.0 미만)
        if min_rating < self.LOW_RATING_THRESHOLD:
            confidence = 0.9 - (min_rating / 5) * 0.3
            return "negative", confidence

        # 평균이 높으면 긍정
        if avg_rating >= self.HIGH_RATING_THRESHOLD:
            confidence = 0.6 + (avg_rating - 4) * 0.3
            return "positive", min(0.95, confidence)

        # 평균이 3.5 이상이면 약한 긍정
        if avg_rating >= 3.5:
            confidence = 0.55 + (avg_rating - 3.5) * 0.2
            return "positive", min(0.75, confidence)

        # 중간
        return "neutral", 0.5

    def _integrate_with_ratings(
        self,
        text_sentiment: SentimentType,
        text_confidence: float,
        rating_sentiment: SentimentType,
        rating_confidence: float,
        ratings: list[float],
    ) -> tuple[SentimentType, float, str]:
        """텍스트 분석과 평점 통합"""
        min_rating = min(ratings)
        avg_rating = sum(ratings) / len(ratings)

        # 규칙 1: 평점이 매우 낮으면 (3점 미만)
        if min_rating < self.LOW_RATING_THRESHOLD:
            if avg_rating < 3.5:
                return "negative", 0.95, "low_rating_override"
            # 하나만 낮고 평균은 괜찮으면 → 중립 (텍스트 무시하지 않음)
            return "neutral", 0.7, "low_rating_tempered"

        # 규칙 2: 텍스트와 평점이 일치하면 높은 신뢰도
        if text_sentiment == rating_sentiment:
            combined = max(text_confidence, rating_confidence)
            return text_sentiment, combined, "text_rating_consensus"

        # 규칙 3: 텍스트는 부정인데 평점이 높으면 → 중립
        if text_sentiment == "negative" and avg_rating >= self.HIGH_RATING_THRESHOLD:
            return "neutral", 0.7, "rating_tempered_negative"

        # 규칙 4: 텍스트는 긍정인데 평점이 낮으면 → 중립
        if text_sentiment == "positive" and avg_rating < self.LOW_RATING_THRESHOLD + 0.5:
            return "neutral", 0.6, "rating_tempered_positive"

        # 그 외: 텍스트 분석 결과 유지
        return text_sentiment, text_confidence * 0.9, "text_preferred"


