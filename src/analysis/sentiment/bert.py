"""
BERT 기반 감정분석
"""
from typing import List, Optional
from .base import SentimentAnalyzer, SentimentResult


class BertAnalyzer(SentimentAnalyzer):
    """
    BERT 기반 감정분석기

    nlptown/bert-base-multilingual-uncased-sentiment 모델을 사용하여
    정밀한 감정 분석을 수행합니다.
    """

    def __init__(
        self,
        model_name: str = "nlptown/bert-base-multilingual-uncased-sentiment",
        device: str = "auto",
        max_length: int = 512,
        batch_size: int = 32
    ):
        """
        Args:
            model_name: HuggingFace 모델 이름
            device: 장치 ('auto', 'cuda', 'cpu')
            max_length: 최대 토큰 길이
            batch_size: 배치 크기
        """
        self.model_name = model_name
        self.max_length = max_length
        self.batch_size = batch_size
        self.pipeline = None
        self._device = device
        self._initialized = False

    def initialize(self) -> bool:
        """
        모델 초기화 (지연 로딩)

        Returns:
            bool: 초기화 성공 여부
        """
        if self._initialized:
            return True

        try:
            from transformers import pipeline as hf_pipeline
            import torch

            # 장치 설정
            if self._device == "auto":
                device = 0 if torch.cuda.is_available() else -1
            elif self._device == "cuda":
                device = 0
            else:
                device = -1

            self.pipeline = hf_pipeline(
                "sentiment-analysis",
                model=self.model_name,
                device=device,
                truncation=True,
                max_length=self.max_length
            )
            self._initialized = True
            return True

        except ImportError:
            print("⚠️ transformers/torch 미설치")
            return False
        except Exception as e:
            print(f"⚠️ BERT 모델 로딩 실패: {e}")
            return False

    def _predict_score(self, text: str) -> float:
        """
        딥러닝 감정 예측 (0~1 점수)

        Args:
            text: 분석할 텍스트

        Returns:
            float: 감정 점수
        """
        if not self.pipeline:
            return 0.5

        try:
            # 텍스트 길이 제한
            text = text[:500] if len(text) > 500 else text
            result = self.pipeline(text)[0]
            label = result['label']

            # nlptown 모델: "1 star" ~ "5 stars"
            if 'star' in label.lower():
                stars = int(label.split()[0])
                return (stars - 1) / 4  # 0~1 정규화

            return 0.5
        except Exception:
            return 0.5

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
                method='bert'
            )

        # 지연 초기화
        if not self._initialized:
            if not self.initialize():
                return SentimentResult(
                    sentiment='neutral',
                    score=0.5,
                    method='bert_fallback'
                )

        score = self._predict_score(text)

        # 감정 판정
        if score >= 0.6:
            sentiment = 'positive'
        elif score >= 0.4:
            sentiment = 'neutral'
        else:
            sentiment = 'negative'

        return SentimentResult(
            sentiment=sentiment,
            score=round(score, 3),
            method='bert'
        )

    def analyze_batch(self, texts: List[str]) -> List[SentimentResult]:
        """
        배치 감정 분석

        Args:
            texts: 분석할 텍스트 리스트

        Returns:
            list[SentimentResult]: 감정분석 결과 리스트
        """
        if not self._initialized:
            if not self.initialize():
                return [
                    SentimentResult(sentiment='neutral', score=0.5, method='bert_fallback')
                    for _ in texts
                ]

        results = []
        for text in texts:
            results.append(self.analyze(text))

        return results

    @property
    def is_available(self) -> bool:
        """BERT 모델 사용 가능 여부"""
        if not self._initialized:
            return self.initialize()
        return self._initialized
