"""
파이프라인 베이스 클래스

BasePipeline: 공통 기능 (키워드 추출, 전처리, 감정 분석) - 비동기

RealtimePipeline이 상속하여 사용합니다.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from core.stopwords import LexiconConfig
from schemas.dto import (
    PipelineResultDTO,
    ProcessedReviewDTO,
    ReviewDTO,
)

# 순환 참조 방지
if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


# =============================================================================
# BasePipeline: 공통 기능 (비동기)
# =============================================================================


class BasePipeline(ABC):
    """
    파이프라인 공통 기능 베이스 클래스 (비동기)

    공통 기능:
    - Kiwi 키워드 추출
    - 전처리/필터링 (욕설, 광고, 빈 리뷰)
    - 감정 분석 (Lexicon 기반)
    - DB 세션 관리 (비동기)
    """

    def __init__(self) -> None:
        from domain.analysis._singletons import (
            get_hybrid_classifier,
            get_kiwi,
            get_sentiment_analyzer,
        )

        self.kiwi = get_kiwi()
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._sentiment_analyzer = get_sentiment_analyzer()
        self._hybrid_classifier = get_hybrid_classifier()

    async def _get_session(self) -> AsyncSession:
        """DB 비동기 세션 획득 (lazy loading)"""
        if self._session_factory is None:
            try:
                from repository.database import get_session_factory

                self._session_factory = get_session_factory()
                logger.info("DB 세션 팩토리 연결 완료")
            except Exception as e:
                logger.warning("DB 세션 팩토리 획득 실패: %s", e)
                raise
        return self._session_factory()

    # =========================================================================
    # 키워드 추출
    # =========================================================================

    def extract_keywords(self, text: str) -> list[str]:
        """
        텍스트에서 키워드 추출 (Kiwi 우선, 정규식 폴백)

        Args:
            text: 분석할 텍스트

        Returns:
            키워드 리스트
        """
        if not text:
            return []

        if self.kiwi:
            try:
                keywords = []
                tokens = self.kiwi.tokenize(text)
                for token in tokens:
                    tag = token.tag
                    word = token.form
                    # 명사(NNG, NNP) + 형용사(VA) + 동사(VV)
                    is_target_pos = tag in ("NNG", "NNP", "VA", "VV", "XR")
                    is_valid = len(word) >= 2 and word not in LexiconConfig.STOP_WORDS
                    if is_target_pos and is_valid:
                        keywords.append(word)
                return keywords
            except Exception as e:
                logger.debug("Kiwi 토큰화 실패, 정규식 폴백: %s", e)

        # 정규식 폴백
        words = re.findall(r"[가-힣]{2,}", text)
        return [w for w in words if w not in LexiconConfig.STOP_WORDS]

    # =========================================================================
    # 전처리/필터링
    # =========================================================================

    def preprocess_review(self, review: ReviewDTO) -> ReviewDTO | None:
        """
        리뷰 전처리 (필터링)

        Args:
            review: ReviewDTO 객체

        Returns:
            통과한 ReviewDTO 또는 None (필터됨)
        """
        # 1. 기본 유효성 검사
        if not review.is_valid():
            return None

        text = review.content

        # 2. 욕설/비방 필터
        text_lower = text.lower()
        for pattern in LexiconConfig.PROFANITY_PATTERNS:
            if pattern in text_lower:
                logger.debug("욕설 필터: %s...", text[:30])
                return None

        # 3. 광고 필터
        for pattern in LexiconConfig.AD_PATTERNS:
            if pattern in text_lower:
                logger.debug("광고 필터: %s...", text[:30])
                return None

        return review

    # =========================================================================
    # 감정 분석
    # =========================================================================

    def analyze_sentiment(
        self, text: str, keywords: list[str] | None = None
    ) -> tuple[str, float]:
        """
        감정 분석 (UnifiedSentimentAnalyzer 기반)

        Args:
            text: 분석할 텍스트
            keywords: 추출된 키워드 리스트 (선택)

        Returns:
            (sentiment, score) - ('positive'/'neutral'/'negative', 0~1)
        """
        if not text:
            return "neutral", 0.5

        result = self._sentiment_analyzer.analyze(text, keywords)
        return result.sentiment, result.confidence

    def analyze_sentiment_with_ratings(
        self,
        text: str,
        keywords: list[str] | None = None,
        rating_service: float | None = None,
        rating_car: float | None = None,
        rating_convenience: float | None = None,
    ) -> tuple[str, float]:
        """
        감정 분석 + 평점 통합

        Args:
            text: 분석할 텍스트
            keywords: 추출된 키워드 리스트
            rating_service: 서비스 평점 (1~5)
            rating_car: 차량 평점 (1~5)
            rating_convenience: 편의성 평점 (1~5)

        Returns:
            (sentiment, score) - ('positive'/'neutral'/'negative', 0~1)
        """
        if not text:
            return "neutral", 0.5

        result = self._sentiment_analyzer.analyze_with_ratings(
            text=text,
            keywords=keywords,
            rating_service=rating_service,
            rating_car=rating_car,
            rating_convenience=rating_convenience,
        )
        return result.sentiment, result.confidence

    # =========================================================================
    # 추상 메서드
    # =========================================================================

    @abstractmethod
    async def run(self, *args, **kwargs) -> PipelineResultDTO:
        """파이프라인 실행 (비동기)"""
        pass
