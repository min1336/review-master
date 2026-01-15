"""
사전 기반 감정분석 (Lexicon-based)
"""
from typing import List
from .base import SentimentAnalyzer, SentimentResult
from ...config.stopwords import LexiconConfig


class LexiconAnalyzer(SentimentAnalyzer):
    """
    사전 기반 감정분석기

    긍정/부정 어휘 사전을 사용하여 빠르게 감정을 분류합니다.
    확실한 경우(score >= 0.7 또는 <= 0.3)에 적합합니다.
    """

    def __init__(
        self,
        positive_words: set = None,
        negative_words: set = None,
        confident_high: float = 0.7,
        confident_low: float = 0.3
    ):
        """
        Args:
            positive_words: 긍정 어휘 집합 (기본값: LexiconConfig.POSITIVE_WORDS)
            negative_words: 부정 어휘 집합 (기본값: LexiconConfig.NEGATIVE_WORDS)
            confident_high: 확실한 긍정 임계값 (기본값: 0.7)
            confident_low: 확실한 부정 임계값 (기본값: 0.3)
        """
        self.positive_words = positive_words or LexiconConfig.POSITIVE_WORDS
        self.negative_words = negative_words or LexiconConfig.NEGATIVE_WORDS
        self.confident_high = confident_high
        self.confident_low = confident_low

    def calculate_score(self, text: str) -> float:
        """
        사전 기반 감정 점수 계산 (0~1)

        Args:
            text: 분석할 텍스트

        Returns:
            float: 감정 점수 (0: 매우 부정, 1: 매우 긍정)
        """
        if not text:
            return 0.5

        pos_count = sum(1 for w in self.positive_words if w in text)
        neg_count = sum(1 for w in self.negative_words if w in text)
        total = pos_count + neg_count

        if total == 0:
            return 0.5

        # -1~1 → 0~1 변환
        raw_score = (pos_count - neg_count) / total
        return (raw_score + 1) / 2

    def analyze(self, text: str) -> SentimentResult:
        """
        텍스트 감정 분석

        Args:
            text: 분석할 텍스트

        Returns:
            SentimentResult: 감정분석 결과
        """
        if not text or not text.strip():
            return SentimentResult(
                sentiment='neutral',
                score=0.5,
                method='lexicon'
            )

        score = self.calculate_score(text)

        # 감정 판정
        if score >= self.confident_high:
            sentiment = 'positive'
        elif score <= self.confident_low:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'

        return SentimentResult(
            sentiment=sentiment,
            score=round(score, 3),
            method='lexicon'
        )

    def analyze_batch(self, texts: List[str]) -> List[SentimentResult]:
        """
        배치 감정 분석

        Args:
            texts: 분석할 텍스트 리스트

        Returns:
            list[SentimentResult]: 감정분석 결과 리스트
        """
        return [self.analyze(text) for text in texts]

    def is_confident(self, score: float) -> bool:
        """
        점수가 확실한 범위인지 확인

        Args:
            score: 감정 점수

        Returns:
            bool: 확실한 범위이면 True
        """
        return score >= self.confident_high or score <= self.confident_low
