"""
하이브리드 태그+감정 분류기 (v2.1)

ABSA + FastEmbed 임베딩을 결합하여 정확도 향상:
1. ABSA: 리뷰 전체를 분석하여 Aspect별 감정 추출 (혼합 감정 처리에 강함)
2. Embedding: 개별 키워드를 태그에 분류 (빠르고 안정적, ONNX 기반)
3. 규칙 기반: 전문 용어 우선 매핑

사용법:
    from domain.analysis import HybridClassifier

    classifier = HybridClassifier()

    # 리뷰 + 키워드 함께 분석
    results = classifier.classify_review(
        review="직원이 친절했지만 차량이 더러웠어요",
        keywords=['직원', '친절', '차량', '더러']
    )
    # {
    #   '직원이 친절함': {'positive': ['직원', '친절'], 'negative': []},
    #   '차량이 청결함': {'positive': [], 'negative': ['차량', '더러']}
    # }
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict

import numpy as np

from .absa import RuleBasedABSA
from .patterns import (
    DOUBLE_NEGATION_REGEX,
    GENERAL_POSITIVE_KEYWORDS,
    NEGATIVE_REGEX,
    POSITIVE_EXCEPTION_REGEX,
    POSITIVE_REGEX,
    RULE_BASED_TAG_MAPPING,
)
from .tag_embeddings import TagEmbeddingManager

logger = logging.getLogger(__name__)


class HybridClassifier:
    """
    하이브리드 태그+감정 분류기

    ABSA + FastEmbed 임베딩 + 규칙 기반 매핑을 결합
    """

    DEFAULT_MODEL = "intfloat/multilingual-e5-large"
    DEFAULT_THRESHOLD = 0.3

    def __init__(
        self,
        model_name: str | None = None,
        similarity_threshold: float = DEFAULT_THRESHOLD,
        lazy_load: bool = True,
    ):
        """
        Args:
            model_name: FastEmbed 모델명 (ONNX 기반)
            similarity_threshold: 최소 유사도 임계값 (미만이면 '기타')
            lazy_load: True면 첫 사용 시 모델 로드
        """
        self.model_name = model_name or self.DEFAULT_MODEL
        self.similarity_threshold = similarity_threshold

        # ABSA
        self._absa = RuleBasedABSA()

        # 임베딩 관련
        self._model = None
        self._tag_manager: TagEmbeddingManager | None = None
        self._tag_embeddings: dict[str, np.ndarray] | None = None
        self._tag_names: list[str] | None = None
        self._initialized = False

        if not lazy_load:
            self._initialize_embedding()

    def _initialize_embedding(self) -> bool:
        """임베딩 모델 초기화"""
        if self._initialized:
            return True

        try:
            logger.info(f"임베딩 모델 로딩 중: {self.model_name}")

            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self.model_name)

            self._tag_manager = TagEmbeddingManager(model=self._model)
            self._tag_embeddings = self._tag_manager.get_or_compute()
            self._tag_names = list(self._tag_embeddings.keys())

            self._initialized = True
            logger.info("HybridClassifier 초기화 완료")
            return True

        except ImportError as e:
            logger.error(f"fastembed 패키지가 필요합니다: {e}")
            return False

        except Exception as e:
            logger.error(f"초기화 실패: {e}")
            return False

    def _ensure_initialized(self):
        """초기화 확인 (지연 로딩)"""
        if not self._initialized and not self._initialize_embedding():
            raise RuntimeError("HybridClassifier 초기화 실패")

    # =========================================================================
    # 감정 분석
    # =========================================================================

    def _detect_sentiment(self, keyword: str) -> str:
        """키워드의 감정 판단 (규칙 기반)"""
        if not keyword:
            return "neutral"

        if POSITIVE_EXCEPTION_REGEX.search(keyword):
            return "positive"

        if NEGATIVE_REGEX.search(keyword):
            return "negative"

        if POSITIVE_REGEX.search(keyword):
            return "positive"

        return "neutral"

    def _detect_sentiment_with_context(
        self, keyword: str, context: str, window_size: int = 20
    ) -> str:
        """문맥을 고려한 키워드 감정 판단"""
        base_sentiment = self._detect_sentiment(keyword)

        if not context or keyword not in context:
            return base_sentiment

        pos = context.find(keyword)
        if pos == -1:
            return base_sentiment

        start = max(0, pos - window_size)
        end = min(len(context), pos + len(keyword) + window_size)
        window = context[start:end]

        # 이중부정 → 긍정
        if DOUBLE_NEGATION_REGEX.search(window):
            return "positive"

        # 긍정 예외
        has_positive_exception = POSITIVE_EXCEPTION_REGEX.search(window)
        if has_positive_exception and base_sentiment in ["positive", "neutral"]:
            return "positive"

        # 부정 표현 패턴
        negation_pattern = re.compile(
            r"지\s*않|지\s*못|못\s*하|(?<![가-힣])안\s*하|안\s*좋|너무\s*안"
        )

        has_negation = negation_pattern.search(window)
        if base_sentiment == "positive" and has_negation and not has_positive_exception:
            return "negative"

        if base_sentiment != "neutral":
            return base_sentiment

        if NEGATIVE_REGEX.search(window):
            return "negative"

        if POSITIVE_REGEX.search(window):
            return "positive"

        return "neutral"

    # =========================================================================
    # 태그 분류 (임베딩 + 규칙)
    # =========================================================================

    def _check_rule_based_mapping(self, keyword: str) -> tuple[str, float] | None:
        """규칙 기반 태그 매핑 확인 (임베딩보다 우선)"""
        keyword_lower = keyword.lower().strip()
        for tag, keywords in RULE_BASED_TAG_MAPPING.items():
            for rule_kw in keywords:
                if keyword_lower == rule_kw or rule_kw in keyword_lower:
                    return (tag, 1.0)
        return None

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """코사인 유사도 계산"""
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot_product / (norm1 * norm2))

    def _classify_keyword(self, keyword: str) -> tuple[str, float]:
        """단일 키워드 태그 분류"""
        self._ensure_initialized()

        if not keyword or not keyword.strip():
            return ("기타", 0.0)

        keyword_lower = keyword.lower().strip()

        # 일반 긍정어는 '기타'로 처리
        if keyword_lower in GENERAL_POSITIVE_KEYWORDS:
            return ("기타", 0.0)

        # 규칙 기반 매핑 우선
        rule_result = self._check_rule_based_mapping(keyword)
        if rule_result:
            return rule_result

        # 임베딩 기반 분류
        keyword_embedding = np.array(list(self._model.embed([keyword])))[0]

        similarities = {}
        for tag_name, tag_embedding in self._tag_embeddings.items():
            sim = self._cosine_similarity(keyword_embedding, tag_embedding)
            similarities[tag_name] = sim

        best_tag = max(similarities, key=similarities.get)
        best_score = similarities[best_tag]

        if best_score < self.similarity_threshold:
            return ("기타", best_score)

        return (best_tag, best_score)

    def _classify_keywords_batch(self, keywords: list[str]) -> list[tuple[str, float]]:
        """배치 키워드 태그 분류"""
        self._ensure_initialized()

        if not keywords:
            return []

        results = [("기타", 0.0) for _ in keywords]
        embedding_indices = []
        embedding_keywords = []

        for i, kw in enumerate(keywords):
            if not kw or not kw.strip():
                continue

            kw_lower = kw.lower().strip()

            if kw_lower in GENERAL_POSITIVE_KEYWORDS:
                results[i] = ("기타", 0.0)
                continue

            rule_result = self._check_rule_based_mapping(kw)
            if rule_result:
                results[i] = rule_result
            else:
                embedding_indices.append(i)
                embedding_keywords.append(kw)

        if not embedding_keywords:
            return results

        # 배치 인코딩
        keyword_embeddings = np.array(list(self._model.embed(embedding_keywords)))

        tag_matrix = np.array([self._tag_embeddings[tag] for tag in self._tag_names])

        # 코사인 유사도 행렬 계산
        kw_norms = np.linalg.norm(keyword_embeddings, axis=1, keepdims=True)
        tag_norms = np.linalg.norm(tag_matrix, axis=1, keepdims=True)

        kw_normalized = keyword_embeddings / (kw_norms + 1e-9)
        tag_normalized = tag_matrix / (tag_norms + 1e-9)

        similarity_matrix = np.dot(kw_normalized, tag_normalized.T)

        for idx, orig_idx in enumerate(embedding_indices):
            scores = similarity_matrix[idx]
            best_idx = np.argmax(scores)
            best_score = float(scores[best_idx])
            best_tag = self._tag_names[best_idx]

            if best_score < self.similarity_threshold:
                results[orig_idx] = ("기타", best_score)
            else:
                results[orig_idx] = (best_tag, best_score)

        return results

    # =========================================================================
    # 공개 API
    # =========================================================================

    def classify_keywords(self, keywords: list[str]) -> list[tuple[str, float, str]]:
        """
        키워드 배치 분류 + 감정 판단

        Args:
            keywords: 키워드 리스트

        Returns:
            [(태그, 점수, 감정), ...]
        """
        classifications = self._classify_keywords_batch(keywords)

        results = []
        for (tag, score), keyword in zip(classifications, keywords, strict=False):
            sentiment = self._detect_sentiment(keyword)
            results.append((tag, score, sentiment))

        return results

    def classify_keywords_with_context(
        self, keywords: list[str], context: str
    ) -> list[tuple[str, float, str]]:
        """
        문맥 기반 키워드 배치 분류 + 감정 판단

        Args:
            keywords: 키워드 리스트
            context: 원본 리뷰 텍스트

        Returns:
            [(태그, 점수, 감정), ...]
        """
        classifications = self._classify_keywords_batch(keywords)

        results = []
        for (tag, score), keyword in zip(classifications, keywords, strict=False):
            sentiment = self._detect_sentiment_with_context(keyword, context)
            results.append((tag, score, sentiment))

        return results

    def classify_review(
        self, review: str, keywords: list[str] = None
    ) -> dict[str, dict[str, list[str]]]:
        """
        리뷰와 키워드를 결합 분석

        Args:
            review: 원본 리뷰 텍스트
            keywords: 추출된 키워드 리스트 (없으면 ABSA만 사용)

        Returns:
            {
                '직원이 친절함': {'positive': ['친절'], 'negative': []},
                '차량이 청결함': {'positive': [], 'negative': ['더러운']}
            }
        """
        self._ensure_initialized()

        result = defaultdict(lambda: {"positive": [], "negative": [], "neutral": []})

        # 1. ABSA로 리뷰 전체 분석
        absa_results = self._absa.analyze(review)

        for item in absa_results:
            aspect = item["aspect"]
            sentiment = item["sentiment"]
            keywords_found = item.get("keywords", [])

            for kw in keywords_found:
                if kw not in result[aspect][sentiment]:
                    result[aspect][sentiment].append(kw)

        # 2. 키워드가 있으면 임베딩 분류기로 추가 분석
        if keywords:
            classifications = self.classify_keywords_with_context(keywords, review)

            for kw, (tag, _score, sentiment) in zip(
                keywords, classifications, strict=False
            ):
                if tag == "기타":
                    continue

                if kw not in result[tag][sentiment]:
                    already_classified = False
                    for sent in ["positive", "negative", "neutral"]:
                        if kw in result[tag][sent]:
                            already_classified = True
                            break

                    if not already_classified:
                        result[tag][sentiment].append(kw)

        return {
            tag: sentiments
            for tag, sentiments in result.items()
            if any(sentiments.values())
        }

    def classify_review_simple(self, review: str) -> list[dict]:
        """ABSA만 사용한 간단 분석"""
        return self._absa.analyze(review)

    def classify_batch_reviews(
        self, reviews: list[str], keywords_list: list[list[str]] = None
    ) -> list[dict[str, dict[str, list[str]]]]:
        """여러 리뷰 배치 분석"""
        results = []

        if keywords_list is None:
            keywords_list = [None] * len(reviews)

        for review, keywords in zip(reviews, keywords_list, strict=False):
            result = self.classify_review(review, keywords)
            results.append(result)

        return results

    def get_review_summary(self, review: str, keywords: list[str] = None) -> dict:
        """
        리뷰 분석 요약 반환

        Returns:
            {
                'aspects': ['직원이 친절함', '차량이 청결함'],
                'overall_sentiment': 'mixed',
                'positive_aspects': ['직원이 친절함'],
                'negative_aspects': ['차량이 청결함'],
                'details': {...}
            }
        """
        details = self.classify_review(review, keywords)

        positive_aspects = []
        negative_aspects = []

        for aspect, sentiments in details.items():
            pos_count = len(sentiments["positive"])
            neg_count = len(sentiments["negative"])

            if pos_count > neg_count:
                positive_aspects.append(aspect)
            elif neg_count > pos_count:
                negative_aspects.append(aspect)

        if positive_aspects and negative_aspects:
            overall = "mixed"
        elif positive_aspects:
            overall = "positive"
        elif negative_aspects:
            overall = "negative"
        else:
            overall = "neutral"

        return {
            "aspects": list(details.keys()),
            "overall_sentiment": overall,
            "positive_aspects": positive_aspects,
            "negative_aspects": negative_aspects,
            "details": dict(details),
        }

    def format_tag_sentiment(
        self, result: dict[str, dict[str, list[str]]], hide_neutral: bool = True
    ) -> str:
        """결과를 태그별감정 형식으로 포맷팅 (예: "직원이 친절함(+), 차량이 청결함(-)")"""
        parts = []

        for tag, sentiments in result.items():
            pos_count = len(sentiments.get("positive", []))
            neg_count = len(sentiments.get("negative", []))

            if pos_count > neg_count:
                parts.append(f"{tag}(+)")
            elif neg_count > pos_count:
                parts.append(f"{tag}(-)")
            elif not hide_neutral:
                parts.append(f"{tag}(0)")

        return ", ".join(parts)

    def get_tag_names(self) -> list[str]:
        """태그 그룹명 목록 반환"""
        self._ensure_initialized()
        return self._tag_names.copy()

    def get_tag_color(self, tag_name: str) -> str:
        """태그 색상 반환"""
        if self._tag_manager:
            return self._tag_manager.get_tag_color(tag_name)
        return "#6b7280"

    @property
    def is_initialized(self) -> bool:
        """초기화 여부"""
        return self._initialized
