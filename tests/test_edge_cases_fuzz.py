"""Edge Case / Fuzz Testing

특수문자, 이모지, 초장문, 빈 값, None, 유니코드, 혼합 언어 등
분석 모듈이 어떤 입력에도 크래시하지 않는지 검증 (Robustness)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

os.environ.setdefault("LIGHTWEIGHT_MODE", "true")

from domain.analysis.absa import RuleBasedABSA
from domain.analysis.chunker import ClauseChunker
from domain.analysis.hybrid_classifier import HybridClassifier
from domain.analysis.patterns import (
    extract_stem,
)
from domain.analysis.sentiment_core import (
    check_double_negation,
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


# ── 특수문자 / 이모지 입력 ────────────────────────────


class TestSpecialCharacters:
    SPECIAL_INPUTS = [
        "👍👍👍 최고예요!",
        "😡😡😡 최악이에요",
        "★★★★★",
        "!!!???...",
        "ㅋㅋㅋㅋㅋ",
        "ㅠㅠㅠㅠㅠ",
        "~!@#$%^&*()",
        "  \t\n  ",
        "1234567890",
        "<script>alert('xss')</script>",
        "SELECT * FROM users;",
        "{{template_injection}}",
    ]

    @pytest.mark.parametrize("text", SPECIAL_INPUTS)
    def test_classifier_no_crash(self, classifier, text):
        result = classifier.classify_review(text)
        assert isinstance(result, dict)

    @pytest.mark.parametrize("text", SPECIAL_INPUTS)
    def test_absa_no_crash(self, absa, text):
        result = absa.analyze(text)
        assert isinstance(result, list)

    @pytest.mark.parametrize("text", SPECIAL_INPUTS)
    def test_chunker_no_crash(self, chunker, text):
        result = chunker.chunk(text)
        assert isinstance(result, list)

    @pytest.mark.parametrize("text", SPECIAL_INPUTS)
    def test_sentiment_functions_no_crash(self, text):
        detect_keyword_sentiment(text)
        count_sentiment_matches(text)
        check_double_negation(text)


# ── 초장문 입력 (Stress Test) ─────────────────────────


class TestLongInputStress:
    def test_very_long_review_classifier(self, classifier):
        review = "직원이 친절했어요. " * 500  # ~5000자
        result = classifier.classify_review(review)
        assert isinstance(result, dict)

    def test_very_long_review_absa(self, absa):
        review = "차가 깨끗하고 가격이 저렴해요. " * 500
        result = absa.analyze(review)
        assert isinstance(result, list)

    def test_very_long_review_chunker(self, chunker):
        review = "좋았지만 아쉬운 점도 있었어요. " * 500
        result = chunker.chunk(review)
        assert isinstance(result, list)
        assert len(result) > 1

    def test_single_very_long_word(self, classifier):
        review = "가" * 10000
        result = classifier.classify_review(review)
        assert isinstance(result, dict)


# ── 빈 값 / None / 경계 입력 ─────────────────────────


class TestEmptyAndBoundaryInputs:
    EMPTY_INPUTS = ["", "  ", "\t", "\n", None]

    @pytest.mark.parametrize("text", EMPTY_INPUTS)
    def test_extract_stem_empty(self, text):
        if text is None:
            # extract_stem은 None을 받으면 None 반환
            result = extract_stem(text)
            assert result is None
        else:
            result = extract_stem(text)
            assert isinstance(result, str)

    def test_classify_review_none_keywords(self, classifier):
        result = classifier.classify_review("친절해요", keywords=None)
        assert isinstance(result, dict)

    def test_classify_review_empty_keywords(self, classifier):
        result = classifier.classify_review("친절해요", keywords=[])
        assert isinstance(result, dict)

    def test_single_char_review(self, classifier):
        result = classifier.classify_review("좋")
        assert isinstance(result, dict)

    def test_two_char_review(self, absa):
        result = absa.analyze("좋아")
        assert isinstance(result, list)


# ── 혼합 언어 입력 ───────────────────────────────────


class TestMixedLanguageInputs:
    MIXED_INPUTS = [
        "very good 친절해요",
        "service가 최고!",
        "car가 dirty했어요",
        "价格很便宜 가격이 싸요",
        "직원 kindly 안내해줬어요",
        "100% 만족합니다",
        "5/5 별점 추천!",
    ]

    @pytest.mark.parametrize("text", MIXED_INPUTS)
    def test_mixed_language_no_crash(self, classifier, text):
        result = classifier.classify_review(text)
        assert isinstance(result, dict)

    @pytest.mark.parametrize("text", MIXED_INPUTS)
    def test_mixed_language_absa(self, absa, text):
        result = absa.analyze(text)
        assert isinstance(result, list)


# ── 반복 패턴 입력 ───────────────────────────────────


class TestRepetitiveInputs:
    def test_repeated_positive_word(self, classifier):
        result = classifier.classify_review("최고최고최고최고최고")
        assert isinstance(result, dict)

    def test_repeated_negative_word(self, classifier):
        result = classifier.classify_review("최악최악최악최악최악")
        assert isinstance(result, dict)

    def test_repeated_same_review(self, classifier):
        """같은 입력에 대해 결정론적 결과"""
        review = "직원이 친절하고 차가 깨끗해요"
        result1 = classifier.classify_review(review)
        result2 = classifier.classify_review(review)
        assert result1 == result2

    def test_all_punctuation(self, absa):
        result = absa.analyze("......!!!!!?????")
        assert isinstance(result, list)

    def test_newlines_only(self, chunker):
        result = chunker.chunk("\n\n\n\n\n")
        assert result == []
