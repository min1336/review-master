"""sentiment_core.py 단위 테스트

감정 판단 프리미티브: 이중부정, 패턴 카운트, 키워드/문맥 감정 판단
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from domain.analysis.sentiment_core import (
    _is_negation_prefixed_only,
    _trim_window_by_adversative,
    check_double_negation,
    count_sentiment_matches,
    detect_keyword_sentiment,
    detect_keyword_sentiment_with_context,
)


# ── check_double_negation ─────────────────────────────


class TestCheckDoubleNegation:
    @pytest.mark.parametrize("text", [
        "불편한 점이 없었어요",
        "문제없이 잘 이용했습니다",
        "나쁘지 않았어요",
        "불편하지 않았습니다",
        "비싸지 않아요",
        "걱정 없이 이용했어요",
        "부담 없이 빌렸습니다",
        "냄새 안 나요",
        "느리지 않았어요",
    ])
    def test_double_negation_detected(self, text):
        assert check_double_negation(text) is True

    @pytest.mark.parametrize("text", [
        "불편했어요",
        "문제가 있었어요",
        "나빴어요",
        "비싸요",
        "친절했어요",
    ])
    def test_single_negation_not_detected(self, text):
        assert check_double_negation(text) is False


# ── count_sentiment_matches ───────────────────────────


class TestCountSentimentMatches:
    def test_positive_only(self):
        pos, neg = count_sentiment_matches("친절하고 깨끗했어요")
        assert pos > 0
        assert neg == 0

    def test_negative_only(self):
        pos, neg = count_sentiment_matches("불친절하고 더러웠어요")
        assert neg > 0

    def test_mixed(self):
        pos, neg = count_sentiment_matches("친절한데 차가 더러워요")
        assert pos > 0
        assert neg > 0

    def test_empty_text(self):
        pos, neg = count_sentiment_matches("")
        assert pos == 0
        assert neg == 0


# ── detect_keyword_sentiment ──────────────────────────


class TestDetectKeywordSentiment:
    @pytest.mark.parametrize("keyword,expected", [
        ("친절", "positive"),
        ("깨끗", "positive"),
        ("저렴", "positive"),
        ("만족", "positive"),
        ("추천", "positive"),
    ])
    def test_positive_keywords(self, keyword, expected):
        assert detect_keyword_sentiment(keyword) == expected

    @pytest.mark.parametrize("keyword,expected", [
        ("불친절", "negative"),
        ("더럽", "negative"),
        ("비싸", "negative"),
        ("불편", "negative"),
        ("최악", "negative"),
    ])
    def test_negative_keywords(self, keyword, expected):
        assert detect_keyword_sentiment(keyword) == expected

    def test_neutral_keyword(self):
        assert detect_keyword_sentiment("자동차") == "neutral"

    def test_empty_keyword(self):
        assert detect_keyword_sentiment("") == "neutral"

    def test_positive_exception_over_negative(self):
        # "부담없" → 긍정 예외가 부정보다 우선
        assert detect_keyword_sentiment("부담없이") == "positive"


# ── detect_keyword_sentiment_with_context ─────────────


class TestDetectKeywordSentimentWithContext:
    def test_negation_prefix_flips_positive(self):
        # "친절"이 "불친절" 안에서만 → negative
        result = detect_keyword_sentiment_with_context(
            "친절", "직원이 불친절했어요"
        )
        assert result == "negative"

    def test_independent_positive_stays_positive(self):
        # "친절"이 독립적으로 사용 → positive
        result = detect_keyword_sentiment_with_context(
            "친절", "직원이 정말 친절했어요"
        )
        assert result == "positive"

    def test_double_negation_in_context_positive(self):
        result = detect_keyword_sentiment_with_context(
            "불편", "불편한 점이 없었어요"
        )
        assert result == "positive"

    def test_keyword_not_in_context_returns_base(self):
        result = detect_keyword_sentiment_with_context(
            "친절", "차가 깨끗했어요"
        )
        assert result == "positive"  # base sentiment of "친절"

    def test_empty_context(self):
        result = detect_keyword_sentiment_with_context("친절", "")
        assert result == "positive"


# ── _is_negation_prefixed_only ────────────────────────


class TestIsNegationPrefixedOnly:
    def test_only_in_negation_prefix(self):
        assert _is_negation_prefixed_only("친절", "직원이 불친절했어요") is True

    def test_both_independent_and_prefixed(self):
        assert _is_negation_prefixed_only(
            "친절", "불친절하지만 친절한 부분도 있어요"
        ) is False

    def test_no_negation_prefix(self):
        assert _is_negation_prefixed_only("친절", "정말 친절합니다") is False

    def test_bi_prefix(self):
        assert _is_negation_prefixed_only("위생", "비위생적이었어요") is True


# ── _trim_window_by_adversative ───────────────────────


class TestTrimWindowByAdversative:
    def test_keyword_before_adversative(self):
        window = "친절했지만 차가 더러웠어요"
        # "친절" is at position 0, "지만" splits the clause
        result = _trim_window_by_adversative(window, 0)
        assert "더러" not in result
        assert "친절" in result

    def test_keyword_after_adversative(self):
        window = "친절했지만 차가 더러웠어요"
        kw_pos = window.index("더러")
        result = _trim_window_by_adversative(window, kw_pos)
        assert "친절" not in result
        assert "더러" in result

    def test_no_adversative(self):
        window = "직원이 친절했어요"
        result = _trim_window_by_adversative(window, 0)
        assert result == window
