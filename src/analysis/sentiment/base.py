"""
감정분석 추상 클래스 및 데이터 클래스
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


@dataclass
class SentimentResult:
    """감정분석 결과"""
    sentiment: Literal['positive', 'neutral', 'negative']
    score: float  # 0.0 ~ 1.0
    method: str  # 'lexicon', 'bert', 'hybrid'

    def to_dict(self) -> dict:
        return {
            'sentiment': self.sentiment,
            'score': self.score,
            'method': self.method
        }


class SentimentAnalyzer(ABC):
    """감정분석 추상 클래스"""

    @abstractmethod
    def analyze(self, text: str) -> SentimentResult:
        """
        텍스트 감정 분석

        Args:
            text: 분석할 텍스트

        Returns:
            SentimentResult: 감정분석 결과
        """
        pass

    @abstractmethod
    def analyze_batch(self, texts: list) -> list:
        """
        배치 감정 분석

        Args:
            texts: 분석할 텍스트 리스트

        Returns:
            list[SentimentResult]: 감정분석 결과 리스트
        """
        pass
