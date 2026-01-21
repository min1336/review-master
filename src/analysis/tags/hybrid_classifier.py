"""
하이브리드 태그+감정 분류기 (v1.0)

두 시스템을 결합하여 정확도 향상:
1. ABSA: 리뷰 전체를 분석하여 Aspect별 감정 추출 (혼합 감정 처리에 강함)
2. Embedding: 개별 키워드를 태그에 분류 (빠르고 안정적)

사용법:
    from src.analysis.tags import HybridClassifier

    classifier = HybridClassifier()

    # 리뷰 + 키워드 함께 분석
    results = classifier.classify_review(
        review="직원이 친절했지만 차량이 더러웠어요",
        keywords=['직원', '친절', '차량', '더러']
    )
    # {
    #   '고객응대': {'positive': ['직원', '친절'], 'negative': []},
    #   '차량청결': {'positive': [], 'negative': ['차량', '더러']}
    # }
"""

import logging
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

from .embedding_classifier import EmbeddingTagClassifier
from ..absa import RuleBasedABSA

logger = logging.getLogger(__name__)


class HybridClassifier:
    """
    하이브리드 태그+감정 분류기

    ABSA와 임베딩 분류기를 결합하여 더 정확한 분류 수행
    """

    def __init__(self, lazy_load: bool = True):
        """
        Args:
            lazy_load: True면 첫 사용 시 모델 로드
        """
        self._embedding_classifier = EmbeddingTagClassifier(lazy_load=lazy_load)
        self._absa = RuleBasedABSA()
        self._initialized = False

    def _ensure_initialized(self):
        """초기화 확인"""
        if not self._initialized:
            self._embedding_classifier._ensure_initialized()
            self._initialized = True

    def classify_review(
        self,
        review: str,
        keywords: List[str] = None
    ) -> Dict[str, Dict[str, List[str]]]:
        """
        리뷰와 키워드를 결합 분석

        Args:
            review: 원본 리뷰 텍스트
            keywords: 추출된 키워드 리스트 (없으면 ABSA만 사용)

        Returns:
            {
                '고객응대': {'positive': ['친절'], 'negative': []},
                '차량청결': {'positive': [], 'negative': ['더러운']}
            }
        """
        self._ensure_initialized()

        result = defaultdict(lambda: {'positive': [], 'negative': [], 'neutral': []})

        # 1. ABSA로 리뷰 전체 분석
        absa_results = self._absa.analyze(review)

        # ABSA 결과를 result에 반영
        for item in absa_results:
            aspect = item['aspect']
            sentiment = item['sentiment']
            keywords_found = item.get('keywords', [])

            for kw in keywords_found:
                if kw not in result[aspect][sentiment]:
                    result[aspect][sentiment].append(kw)

        # 2. 키워드가 있으면 임베딩 분류기로 추가 분석
        if keywords:
            # 임베딩 기반 분류
            classifications = self._embedding_classifier.classify_batch_with_sentiment(keywords)

            for kw, (tag, score, sentiment) in zip(keywords, classifications):
                if tag == '기타':
                    continue

                # ABSA 결과와 병합 (중복 제거)
                if kw not in result[tag][sentiment]:
                    # ABSA에서 이미 다른 감정으로 분류했는지 확인
                    already_classified = False
                    for sent in ['positive', 'negative', 'neutral']:
                        if kw in result[tag][sent]:
                            already_classified = True
                            break

                    if not already_classified:
                        result[tag][sentiment].append(kw)

        # 빈 태그 제거
        return {tag: sentiments for tag, sentiments in result.items()
                if any(sentiments.values())}

    def classify_review_simple(self, review: str) -> List[Dict]:
        """
        ABSA만 사용한 간단 분석

        Args:
            review: 원본 리뷰 텍스트

        Returns:
            [{'aspect': '고객응대', 'sentiment': 'positive', 'opinion': '...'}]
        """
        return self._absa.analyze(review)

    def classify_keywords(
        self,
        keywords: List[str]
    ) -> List[Tuple[str, float, str]]:
        """
        키워드만 분류 (기존 방식)

        Args:
            keywords: 키워드 리스트

        Returns:
            [(태그, 점수, 감정), ...]
        """
        self._ensure_initialized()
        return self._embedding_classifier.classify_batch_with_sentiment(keywords)

    def classify_batch_reviews(
        self,
        reviews: List[str],
        keywords_list: List[List[str]] = None
    ) -> List[Dict[str, Dict[str, List[str]]]]:
        """
        여러 리뷰 배치 분석

        Args:
            reviews: 리뷰 리스트
            keywords_list: 각 리뷰의 키워드 리스트 (없으면 None)

        Returns:
            [리뷰1 결과, 리뷰2 결과, ...]
        """
        results = []

        if keywords_list is None:
            keywords_list = [None] * len(reviews)

        for review, keywords in zip(reviews, keywords_list):
            result = self.classify_review(review, keywords)
            results.append(result)

        return results

    def get_review_summary(
        self,
        review: str,
        keywords: List[str] = None
    ) -> Dict:
        """
        리뷰 분석 요약 반환

        Args:
            review: 원본 리뷰
            keywords: 키워드 리스트

        Returns:
            {
                'aspects': ['고객응대', '차량청결'],
                'overall_sentiment': 'mixed',  # positive, negative, mixed, neutral
                'positive_aspects': ['고객응대'],
                'negative_aspects': ['차량청결'],
                'details': {...}
            }
        """
        details = self.classify_review(review, keywords)

        positive_aspects = []
        negative_aspects = []

        for aspect, sentiments in details.items():
            pos_count = len(sentiments['positive'])
            neg_count = len(sentiments['negative'])

            if pos_count > neg_count:
                positive_aspects.append(aspect)
            elif neg_count > pos_count:
                negative_aspects.append(aspect)

        # 전체 감정 판단
        if positive_aspects and negative_aspects:
            overall = 'mixed'
        elif positive_aspects:
            overall = 'positive'
        elif negative_aspects:
            overall = 'negative'
        else:
            overall = 'neutral'

        return {
            'aspects': list(details.keys()),
            'overall_sentiment': overall,
            'positive_aspects': positive_aspects,
            'negative_aspects': negative_aspects,
            'details': dict(details)
        }

    def format_tag_sentiment(
        self,
        result: Dict[str, Dict[str, List[str]]],
        hide_neutral: bool = True
    ) -> str:
        """
        결과를 태그별감정 형식으로 포맷팅

        Args:
            result: classify_review 결과
            hide_neutral: True면 중립(0) 태그 숨김 (기본값: True)

        예: "고객응대(+), 차량청결(-)"
        """
        parts = []

        for tag, sentiments in result.items():
            pos_count = len(sentiments.get('positive', []))
            neg_count = len(sentiments.get('negative', []))

            if pos_count > neg_count:
                parts.append(f"{tag}(+)")
            elif neg_count > pos_count:
                parts.append(f"{tag}(-)")
            elif not hide_neutral:
                # 중립 표시 옵션이 켜져있을 때만 표시
                parts.append(f"{tag}(0)")
            # hide_neutral=True이고 pos_count == neg_count면 건너뜀

        return ', '.join(parts)
