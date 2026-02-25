"""Step 1: 전처리 + 키워드 추출 + 감정 분석 + 태그 분류"""

from __future__ import annotations

import logging
import re

from core.constants import NEGATIVE_RATING_THRESHOLD
from core.stopwords import LexiconConfig
from schemas.dto import ProcessedReviewDTO, ReviewDTO

logger = logging.getLogger(__name__)


class ReviewPreprocessor:
    """전처리 + 키워드 추출 + 감정 분석 + 태그 분류"""

    def __init__(self) -> None:
        self._kiwi = None
        self._sentiment_analyzer = None
        self._hybrid_classifier = None
        self._init_kiwi()

    def _init_kiwi(self) -> None:
        """Kiwi 형태소 분석기 초기화"""
        try:
            from kiwipiepy import Kiwi

            self._kiwi = Kiwi()
            logger.info("Kiwi 형태소 분석기 초기화 완료")
        except ImportError:
            logger.warning("Kiwi 미설치 - 정규식 폴백 사용")

    def process_batch(self, reviews: list[dict]) -> list[ProcessedReviewDTO]:
        """리뷰 배치를 ProcessedReviewDTO로 변환"""
        if self._sentiment_analyzer is None:
            from domain.analysis import UnifiedSentimentAnalyzer

            self._sentiment_analyzer = UnifiedSentimentAnalyzer(lazy_load=True)
        if self._hybrid_classifier is None:
            from domain.analysis import HybridClassifier

            self._hybrid_classifier = HybridClassifier(lazy_load=True)

        results: list[ProcessedReviewDTO] = []
        for raw in reviews:
            review = ReviewDTO.from_athena_row(raw)

            if not self._preprocess(review):
                continue

            keywords = self._extract_keywords(review.content)

            sentiment, score = self._analyze_sentiment_with_ratings(
                text=review.content,
                keywords=keywords,
                rating_service=self._safe_float(raw.get("rating_service")),
                rating_car=self._safe_float(raw.get("rating_car")),
                rating_convenience=self._safe_float(raw.get("rating_convenience")),
            )

            tag_sentiments = self._hybrid_classifier.classify_review(
                review=review.content, keywords=keywords
            )

            results.append(
                ProcessedReviewDTO(
                    review=review,
                    keywords=keywords,
                    sentiment=sentiment,
                    sentiment_score=score,
                    tag_sentiments=tag_sentiments,
                    rating_car=self._safe_float(raw.get("rating_car")),
                    rating_convenience=self._safe_float(raw.get("rating_convenience")),
                )
            )

        return results

    def _preprocess(self, review: ReviewDTO) -> bool:
        """유효성 + 욕설/광고 필터"""
        if not review.is_valid():
            return False
        text_lower = review.content.lower()
        for pattern in LexiconConfig.PROFANITY_PATTERNS:
            if pattern in text_lower:
                return False
        for pattern in LexiconConfig.AD_PATTERNS:
            if pattern in text_lower:
                return False
        return True

    def _extract_keywords(self, text: str) -> list[str]:
        """키워드 추출 (Kiwi 우선, 정규식 폴백)"""
        if not text:
            return []

        if self._kiwi:
            try:
                keywords = []
                tokens = self._kiwi.tokenize(text)
                for token in tokens:
                    tag = token.tag
                    word = token.form
                    is_target_pos = tag in ("NNG", "NNP", "VA", "VV", "XR")
                    is_valid = len(word) >= 2 and word not in LexiconConfig.STOP_WORDS
                    if is_target_pos and is_valid:
                        keywords.append(word)
                return keywords
            except Exception:
                pass

        words = re.findall(r"[가-힣]{2,}", text)
        return [w for w in words if w not in LexiconConfig.STOP_WORDS]

    def _analyze_sentiment_with_ratings(
        self,
        text: str,
        keywords: list[str],
        rating_service: float | None,
        rating_car: float | None,
        rating_convenience: float | None,
    ) -> tuple[str, float]:
        """텍스트 분석 + 별점 결합 — UnifiedSentimentAnalyzer에 위임"""
        if not text or len(text.strip()) < 5:
            return self._analyze_by_rating(rating_service, rating_car, rating_convenience)

        result = self._sentiment_analyzer.analyze_with_ratings(
            text=text,
            keywords=keywords,
            rating_service=rating_service,
            rating_car=rating_car,
            rating_convenience=rating_convenience,
        )
        return result.sentiment, result.confidence

    def _analyze_by_rating(
        self,
        rating_service: float | None,
        rating_car: float | None,
        rating_convenience: float | None,
    ) -> tuple[str, float]:
        """별점만으로 감정 판단"""
        valid_ratings = [
            r for r in [rating_service, rating_car, rating_convenience] if r is not None
        ]
        if not valid_ratings:
            return "neutral", 0.5

        # 개별 차원 하한 검증: 하나라도 3.0 미만이면 positive 불가
        if any(r < NEGATIVE_RATING_THRESHOLD for r in valid_ratings):
            avg_rating = sum(valid_ratings) / len(valid_ratings)
            if avg_rating >= 3.5:
                return "neutral", 0.5
            return "negative", 0.8

        avg_rating = sum(valid_ratings) / len(valid_ratings)
        if avg_rating >= 4.0:
            return "positive", 0.8
        elif avg_rating >= 3.5:
            return "positive", 0.65
        elif avg_rating >= NEGATIVE_RATING_THRESHOLD:
            return "neutral", 0.5
        else:
            return "negative", 0.8

    @staticmethod
    def _safe_float(val) -> float | None:
        try:
            return float(val) if val else None
        except (ValueError, TypeError):
            return None
