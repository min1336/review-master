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
    #   '직원친절': {'positive': ['직원', '친절'], 'negative': []},
    #   '청결': {'positive': [], 'negative': ['차량', '더러']}
    # }
"""

from __future__ import annotations

import logging
import warnings
from collections import defaultdict

import numpy as np

from .absa import RuleBasedABSA, resolve_tag_conflicts
from core.constants import (
    CONTEXT_WINDOW_SIZE,
    EMBEDDING_MODEL,
    LIGHTWEIGHT_MODE,
    SIMILARITY_THRESHOLD,
)

from .patterns import (
    CONCESSION_REGEX,
    GENERAL_POSITIVE_KEYWORDS,
    RULE_BASED_TAG_MAPPING,
    extract_stem,
)
from .sentiment_core import (
    detect_keyword_sentiment,
    detect_keyword_sentiment_with_context,
)
from .tag_embeddings import TagEmbeddingManager

logger = logging.getLogger(__name__)


class HybridClassifier:
    """
    하이브리드 태그+감정 분류기

    ABSA + FastEmbed 임베딩 + 규칙 기반 매핑을 결합
    """

    DEFAULT_MODEL = EMBEDDING_MODEL
    DEFAULT_THRESHOLD = SIMILARITY_THRESHOLD

    # 임베딩 분류에 부적합한 범용 키워드 (문맥 없이 카테고리 결정 불가)
    _GENERIC_KEYWORDS: set[str] = {
        "상태", "필요", "부분", "장소", "개선", "괜찮",
        "불편", "정도", "느낌", "전체", "전반",
    }

    def __init__(
        self,
        model_name: str | None = None,
        similarity_threshold: float = DEFAULT_THRESHOLD,
        lazy_load: bool = True,
        embedding_enabled: bool | None = None,
    ):
        """
        Args:
            model_name: FastEmbed 모델명 (ONNX 기반)
            similarity_threshold: 최소 유사도 임계값 (미만이면 '기타')
            lazy_load: True면 첫 사용 시 모델 로드
            embedding_enabled: 임베딩 사용 여부 (None이면 LIGHTWEIGHT_MODE에 따름)
        """
        self.model_name = model_name or self.DEFAULT_MODEL
        self.similarity_threshold = similarity_threshold
        self._embedding_enabled = not LIGHTWEIGHT_MODE if embedding_enabled is None else embedding_enabled

        # ABSA
        self._absa = RuleBasedABSA()

        # 규칙 기반 역인덱스 — O(1) 정확/어간 매칭, O(N) 부분문자열 폴백
        self._rule_exact_map: dict[str, str] = {}
        self._rule_substr_pairs: list[tuple[str, str]] = []
        for tag, kws in RULE_BASED_TAG_MAPPING.items():
            for rule_kw in kws:
                if rule_kw not in self._rule_exact_map:
                    self._rule_exact_map[rule_kw] = tag
                self._rule_substr_pairs.append((rule_kw, tag))

        # 임베딩 관련
        self._model = None
        self._tag_manager: TagEmbeddingManager | None = None
        self._tag_embeddings: dict[str, np.ndarray] | None = None
        self._tag_names: list[str] | None = None
        self._tag_matrix: np.ndarray | None = None
        self._tag_matrix_normalized: np.ndarray | None = None
        self._initialized = False

        if not self._embedding_enabled:
            self._initialized = True
            logger.info("HybridClassifier: 경량 모드 (임베딩 비활성화)")
        elif not lazy_load:
            self._initialize_embedding()

    def _initialize_embedding(self) -> bool:
        """임베딩 모델 초기화"""
        if self._initialized:
            return True

        try:
            logger.info(f"임베딩 모델 로딩 중: {self.model_name}")

            from fastembed import TextEmbedding

            warnings.filterwarnings(
                "ignore",
                message=".*now uses mean pooling.*",
                category=UserWarning,
            )
            self._model = TextEmbedding(model_name=self.model_name)

            self._tag_manager = TagEmbeddingManager(model=self._model)
            self._tag_embeddings = self._tag_manager.get_or_compute()
            self._tag_names = list(self._tag_embeddings.keys())
            self._tag_matrix = np.array(
                [self._tag_embeddings[tag] for tag in self._tag_names]
            )
            tag_norms = np.linalg.norm(self._tag_matrix, axis=1, keepdims=True)
            self._tag_matrix_normalized = self._tag_matrix / (tag_norms + 1e-9)

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
    # 감정 분석 — sentiment_core 모듈 위임
    # =========================================================================

    @staticmethod
    def _detect_sentiment(keyword: str) -> str:
        """키워드의 감정 판단 (규칙 기반)"""
        return detect_keyword_sentiment(keyword)

    @staticmethod
    def _detect_sentiment_with_context(
        keyword: str, context: str, window_size: int = CONTEXT_WINDOW_SIZE
    ) -> str:
        """문맥을 고려한 키워드 감정 판단"""
        return detect_keyword_sentiment_with_context(keyword, context, window_size)

    # =========================================================================
    # 태그 분류 (임베딩 + 규칙)
    # =========================================================================

    def _check_rule_based_mapping(self, keyword: str) -> tuple[str, float] | None:
        """규칙 기반 태그 매핑 확인 (역인덱스 사용)

        매칭 전략:
        1. 정확 일치 — O(1) dict lookup
        2. 어간 일치 — O(1) dict lookup
        3. 부분 문자열 일치 — O(N) 폴백 (드문 경로)
        """
        keyword_lower = keyword.lower().strip()

        # O(1) 정확 일치
        tag = self._rule_exact_map.get(keyword_lower)
        if tag:
            return (tag, 1.0)

        # O(1) 어간 일치
        keyword_stem = extract_stem(keyword_lower)
        if keyword_stem:
            tag = self._rule_exact_map.get(keyword_stem)
            if tag:
                return (tag, 1.0)

        # O(N) 부분 문자열 폴백
        for rule_kw, tag in self._rule_substr_pairs:
            if rule_kw in keyword_lower:
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

        # 범용 키워드: 문맥 없이 카테고리 결정 불가 → 규칙 매칭만 시도
        if keyword_lower in self._GENERIC_KEYWORDS:
            rule_result = self._check_rule_based_mapping(keyword)
            if rule_result:
                return rule_result
            return ("기타", 0.0)

        # 일반 긍정어 처리: 규칙 매칭만 시도 (임베딩 오분류 방지)
        if keyword_lower in GENERAL_POSITIVE_KEYWORDS:
            rule_result = self._check_rule_based_mapping(keyword)
            if rule_result:
                return rule_result
            return ("기타", 0.0)

        # 규칙 기반 매핑 우선
        rule_result = self._check_rule_based_mapping(keyword)
        if rule_result:
            return rule_result

        # 경량 모드: 규칙에 없으면 기타
        if not self._embedding_enabled:
            return ("기타", 0.0)

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

            # 범용 키워드: 규칙 매칭만 시도
            if kw_lower in self._GENERIC_KEYWORDS:
                rule_result = self._check_rule_based_mapping(kw)
                if rule_result:
                    results[i] = rule_result
                continue

            # 일반 긍정어: 규칙 매칭만 시도 (임베딩 오분류 방지)
            if kw_lower in GENERAL_POSITIVE_KEYWORDS:
                rule_result = self._check_rule_based_mapping(kw)
                if rule_result:
                    results[i] = rule_result
                continue

            rule_result = self._check_rule_based_mapping(kw)
            if rule_result:
                results[i] = rule_result
            else:
                embedding_indices.append(i)
                embedding_keywords.append(kw)

        if not embedding_keywords or not self._embedding_enabled:
            return results

        # 배치 인코딩
        keyword_embeddings = np.array(list(self._model.embed(embedding_keywords)))

        # 코사인 유사도 행렬 계산 (tag_matrix_normalized는 초기화 시 캐시됨)
        kw_norms = np.linalg.norm(keyword_embeddings, axis=1, keepdims=True)
        kw_normalized = keyword_embeddings / (kw_norms + 1e-9)

        similarity_matrix = np.dot(kw_normalized, self._tag_matrix_normalized.T)

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
                '직원친절': {'positive': ['친절'], 'negative': []},
                '청결': {'positive': [], 'negative': ['더러운']}
            }
        """
        self._ensure_initialized()

        result = defaultdict(lambda: {"positive": [], "negative": [], "neutral": []})

        # 1. ABSA로 리뷰 전체 분석 (절별 감정 유지 — merge 손실 방지)
        absa_tag_groups = self._absa.classify_review(review)

        for aspect, sentiments in absa_tag_groups.items():
            for sent_type in ("positive", "negative", "neutral"):
                for kw in sentiments.get(sent_type, []):
                    if kw not in result[aspect][sent_type]:
                        result[aspect][sent_type].append(kw)

        # ABSA가 분류한 키워드 수집 (임베딩 재분류 방지)
        absa_classified = set()
        for sentiments in result.values():
            for sent_type in ("positive", "negative", "neutral"):
                absa_classified.update(sentiments[sent_type])

        # 2. 키워드가 있으면 임베딩 분류기로 추가 분석 (ABSA 미분류 키워드만)
        if keywords:
            classifications = self.classify_keywords_with_context(keywords, review)

            for kw, (tag, _score, sentiment) in zip(
                keywords, classifications, strict=False
            ):
                if tag == "기타" or kw in absa_classified:
                    continue

                if kw not in result[tag][sentiment]:
                    already_classified = False
                    for sent in ["positive", "negative", "neutral"]:
                        if kw in result[tag][sent]:
                            already_classified = True
                            break

                    if not already_classified:
                        result[tag][sentiment].append(kw)

        # 양보/반전 구문 체크
        has_concession = bool(CONCESSION_REGEX.search(review))

        # 동일 카테고리 positive+negative 충돌 해소 (ABSA 후 임베딩 추가로 발생 가능)
        return resolve_tag_conflicts(dict(result), has_concession)

    def get_review_summary(self, review: str, keywords: list[str] = None) -> dict:
        """
        리뷰 분석 요약 반환

        Returns:
            {
                'aspects': ['직원친절', '청결'],
                'overall_sentiment': 'mixed',
                'positive_aspects': ['직원친절'],
                'negative_aspects': ['청결'],
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

    def get_tag_color(self, tag_name: str) -> str:
        """태그 색상 반환"""
        if self._tag_manager:
            return self._tag_manager.get_tag_color(tag_name)
        return "#6b7280"

    @property
    def is_initialized(self) -> bool:
        """초기화 여부"""
        return self._initialized
