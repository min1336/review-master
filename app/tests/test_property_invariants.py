"""Property-based / Invariant Testing

입력에 관계없이 항상 성립해야 하는 불변식(invariant) 검증
hypothesis 없이 수동 property 테스트로 구현
"""

import sys
import os
import random
import string

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

os.environ.setdefault("LIGHTWEIGHT_MODE", "true")

from domain.analysis.absa import RuleBasedABSA, resolve_tag_conflicts
from domain.analysis.chunker import ClauseChunker
from domain.analysis.hybrid_classifier import HybridClassifier
from domain.analysis.patterns import (
    TAG_REGISTRY,
    TAG_TO_CATEGORY,
    RULE_BASED_TAG_MAPPING,
    extract_stem,
)
from domain.analysis.sentiment_core import (
    count_sentiment_matches,
    detect_keyword_sentiment,
)


@pytest.fixture(scope="module")
def classifier():
    return HybridClassifier(embedding_enabled=False)


@pytest.fixture(scope="module")
def absa():
    return RuleBasedABSA()


@pytest.fixture(scope="module")
def chunker():
    return ClauseChunker(use_punctuation=True)


# ── 불변식: extract_stem 길이 ─────────────────────────


class TestExtractStemInvariants:
    """Property: extract_stem(x)의 길이는 항상 x 이하"""

    KOREAN_WORDS = [
        "친절한", "깨끗함", "불편했다", "만족합니다", "서비스",
        "좋은", "나쁜", "편리하게", "안전적", "경제적",
        "빠르게", "느리게", "높은", "낮은", "좋았습니다",
    ]

    @pytest.mark.parametrize("word", KOREAN_WORDS)
    def test_stem_not_longer_than_original(self, word):
        stem = extract_stem(word)
        assert len(stem) <= len(word)

    @pytest.mark.parametrize("word", KOREAN_WORDS)
    def test_stem_not_empty_for_nonempty_input(self, word):
        stem = extract_stem(word)
        assert len(stem) >= 1


# ── 불변식: sentiment 3값 중 하나 ─────────────────────


class TestSentimentInvariants:
    """Property: 감정 판단은 항상 positive/negative/neutral 중 하나"""

    KEYWORDS = [
        "친절", "불친절", "깨끗", "더럽", "좋은", "나쁜",
        "만족", "불만", "빠른", "느린", "asdf", "12345", "",
    ]

    @pytest.mark.parametrize("keyword", KEYWORDS)
    def test_sentiment_is_valid_enum(self, keyword):
        result = detect_keyword_sentiment(keyword)
        assert result in ("positive", "negative", "neutral")


# ── 불변식: count_sentiment_matches 비음수 ────────────


class TestCountSentimentInvariants:
    """Property: 긍정/부정 카운트는 항상 >= 0"""

    TEXTS = [
        "좋은 서비스", "나쁜 경험", "", "12345",
        "친절하지만 더러워요", "최고!!!", "ㅠㅠ",
    ]

    @pytest.mark.parametrize("text", TEXTS)
    def test_counts_non_negative(self, text):
        pos, neg = count_sentiment_matches(text)
        assert pos >= 0
        assert neg >= 0


# ── 불변식: classify_review 출력 구조 ─────────────────


class TestClassifyReviewInvariants:
    """Property: classify_review는 항상 dict[str, dict[str, list[str]]] 반환"""

    REVIEWS = [
        "직원이 친절했어요",
        "더럽고 비싸요",
        "",
        "좋아요",
        "123",
        "abcdefg",
        "직원은 친절한데 차가 더러웠어요. 가격은 괜찮았습니다",
    ]

    @pytest.mark.parametrize("review", REVIEWS)
    def test_output_is_dict(self, classifier, review):
        result = classifier.classify_review(review)
        assert isinstance(result, dict)

    @pytest.mark.parametrize("review", REVIEWS)
    def test_output_values_are_sentiment_dicts(self, classifier, review):
        result = classifier.classify_review(review)
        for tag, sentiments in result.items():
            assert isinstance(sentiments, dict)
            assert set(sentiments.keys()) == {"positive", "negative", "neutral"}
            for key in ("positive", "negative", "neutral"):
                assert isinstance(sentiments[key], list)

    @pytest.mark.parametrize("review", REVIEWS)
    def test_all_tags_in_registry(self, classifier, review):
        result = classifier.classify_review(review)
        valid = set(TAG_REGISTRY.keys())
        for tag in result.keys():
            assert tag in valid


# ── 불변식: resolve_tag_conflicts 멱등성 ─────────────


class TestResolveTagConflictsInvariants:
    """Property: resolve_tag_conflicts 2회 적용해도 결과 동일 (멱등)"""

    def test_idempotent(self):
        tags = {
            "직원친절": {
                "positive": ["친절", "상냥"],
                "negative": ["불친절"],
                "neutral": [],
            },
            "청결": {
                "positive": ["깨끗"],
                "negative": ["더러", "냄새"],
                "neutral": [],
            },
        }
        result1 = resolve_tag_conflicts(tags, has_concession=False)
        result2 = resolve_tag_conflicts(result1, has_concession=False)
        assert result1 == result2


# ── 불변식: Chunker 출력 ─────────────────────────────


class TestChunkerInvariants:
    """Property: chunker 결과는 빈 문자열을 포함하지 않음"""

    TEXTS = [
        "좋았어요",
        "친절하고 깨끗해요",
        "좋았지만 비싸요. 그런데 친절해요",
        "",
        "   ",
    ]

    @pytest.mark.parametrize("text", TEXTS)
    def test_no_empty_chunks(self, chunker, text):
        chunks = chunker.chunk(text)
        for chunk in chunks:
            assert chunk.strip() != ""
            assert len(chunk.strip()) >= 3  # min_chunk_length default


# ── 불변식: TAG_REGISTRY 구조적 정합성 ───────────────


class TestRegistryStructuralInvariants:
    def test_no_duplicate_tags_across_categories(self):
        """Property: 태그명이 카테고리 간 중복되면 안 됨"""
        seen = {}
        for cat_name, cat in TAG_REGISTRY.items():
            for tag_name in cat.tags:
                assert tag_name not in seen, (
                    f"Duplicate tag '{tag_name}': {seen[tag_name]} vs {cat_name}"
                )
                seen[tag_name] = cat_name

    def test_tag_to_category_is_bijection(self):
        """Property: TAG_TO_CATEGORY의 모든 값은 TAG_REGISTRY의 키"""
        for tag, cat in TAG_TO_CATEGORY.items():
            assert cat in TAG_REGISTRY

    def test_rule_based_mapping_keys_in_registry(self):
        """Property: RULE_BASED_TAG_MAPPING의 모든 키는 TAG_REGISTRY 태그"""
        all_tags = set()
        for cat in TAG_REGISTRY.values():
            all_tags.update(cat.tags.keys())
        for tag in RULE_BASED_TAG_MAPPING:
            assert tag in all_tags


# ── 불변식: 랜덤 한글 입력 ────────────────────────────


class TestRandomKoreanInputInvariants:
    """무작위 한글 조합에 대해 불변식 검증"""

    @staticmethod
    def _random_korean(length: int) -> str:
        # 한글 유니코드 범위: 0xAC00 ~ 0xD7A3
        return "".join(chr(random.randint(0xAC00, 0xD7A3)) for _ in range(length))

    @pytest.mark.parametrize("_", range(10))
    def test_random_korean_no_crash(self, classifier, _):
        text = self._random_korean(random.randint(5, 100))
        result = classifier.classify_review(text)
        assert isinstance(result, dict)

    @pytest.mark.parametrize("_", range(10))
    def test_random_korean_sentiment_valid(self, _):
        text = self._random_korean(random.randint(2, 20))
        sentiment = detect_keyword_sentiment(text)
        assert sentiment in ("positive", "negative", "neutral")

    @pytest.mark.parametrize("_", range(10))
    def test_random_mixed_no_crash(self, classifier, _):
        korean = self._random_korean(random.randint(3, 30))
        ascii_part = "".join(random.choices(string.ascii_letters, k=10))
        digits = "".join(random.choices(string.digits, k=5))
        text = f"{korean} {ascii_part} {digits}"
        result = classifier.classify_review(text)
        assert isinstance(result, dict)
