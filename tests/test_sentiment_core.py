"""
sentiment_core.py 단위 테스트

대상 함수:
- check_double_negation(text) -> bool
- count_sentiment_matches(text) -> (pos_count, neg_count)
- detect_keyword_sentiment(keyword) -> str
- detect_keyword_sentiment_with_context(text, keyword) -> str
- _is_negation_prefixed_only(keyword, text) -> bool
- _trim_window_by_adversative(window, kw_pos) -> str
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from domain.analysis.sentiment_core import (
    _is_negation_prefixed_only,
    _trim_window_by_adversative,
    check_double_negation,
    count_sentiment_matches,
    detect_keyword_sentiment,
    detect_keyword_sentiment_with_context,
)


# =============================================================================
# check_double_negation
# =============================================================================


class TestCheckDoubleNegation:
    """check_double_negation(text) -> bool"""

    def test_나쁘지않다_is_double_negation(self):
        """'나쁘지 않다' → 이중부정 → True"""
        assert check_double_negation("나쁘지 않다") is True

    def test_불편하지않다_is_double_negation(self):
        """'불편하지 않았어요' → 이중부정 → True"""
        assert check_double_negation("불편하지 않았어요") is True

    def test_없지않다_is_double_negation(self):
        """'없지 않은 서비스' → 이중부정 → True"""
        assert check_double_negation("없지 않은 서비스") is True

    def test_그다지_좋지않_is_NOT_double_negation(self):
        """'그다지 좋지 않았다' → 부정 극성 부사(강조) → False"""
        assert check_double_negation("그다지 좋지 않았다") is False

    def test_기다리지않았다_is_double_negation(self):
        """'기다리지 않았다' → 배차/시간 이중부정 → True"""
        assert check_double_negation("기다리지 않았다") is True

    def test_기다림없이_is_double_negation(self):
        """'기다림 없이 바로 배차' → 배차/시간 이중부정 → True"""
        assert check_double_negation("기다림 없이 바로 배차") is True

    def test_대기없이_is_double_negation(self):
        """'대기 없이 빠르게 진행' → 이중부정 → True"""
        assert check_double_negation("대기 없이 빠르게 진행") is True

    def test_불편함없이_is_double_negation(self):
        """'불편함 없이 이용했습니다' → 이중부정 → True"""
        assert check_double_negation("불편함 없이 이용했습니다") is True

    def test_문제없_is_double_negation(self):
        """'문제 없이 반납했습니다' → 이중부정 → True"""
        assert check_double_negation("문제 없이 반납했습니다") is True

    def test_나쁘다_is_not_double_negation(self):
        """'나쁘다' → 단순 부정 → False"""
        assert check_double_negation("나쁘다") is False

    def test_불편하다_is_not_double_negation(self):
        """'불편하다' → 단순 부정 → False"""
        assert check_double_negation("불편하다") is False

    def test_empty_text_is_not_double_negation(self):
        """빈 문자열 → False"""
        assert check_double_negation("") is False

    def test_short_neutral_text_is_not_double_negation(self):
        """'좋아요' → 이중부정 아님 → False"""
        assert check_double_negation("좋아요") is False

    def test_별다른_없_is_double_negation(self):
        """'별다른 문제 없었어요' → 이중부정 → True"""
        assert check_double_negation("별다른 문제 없었어요") is True

    def test_그다지_나쁘지않_is_double_negation(self):
        """'그다지 나쁘지 않았다' → 이중부정 → True"""
        assert check_double_negation("그다지 나쁘지 않았다") is True


# =============================================================================
# count_sentiment_matches
# =============================================================================


class TestCountSentimentMatches:
    """count_sentiment_matches(text) -> (pos_count, neg_count)"""

    def test_pure_positive_text(self):
        """순수 긍정 텍스트: 친절하고 좋았어요 → pos >= 1, neg == 0"""
        pos, neg = count_sentiment_matches("친절하고 좋았어요")
        assert pos >= 1
        assert neg == 0

    def test_pure_negative_text(self):
        """순수 부정 텍스트: 불친절하고 더러웠다 → neg >= 1"""
        pos, neg = count_sentiment_matches("불친절하고 더러웠다")
        assert neg >= 1

    def test_mixed_text_has_both(self):
        """혼합 텍스트: 친절하지만 불편했다 → pos >= 1, neg >= 1"""
        pos, neg = count_sentiment_matches("친절하지만 불편했다")
        assert pos >= 1
        assert neg >= 1

    def test_neutral_text_returns_zeros(self):
        """중립 텍스트: '배차했다' → pos == 0, neg == 0"""
        pos, neg = count_sentiment_matches("배차했다")
        assert pos == 0
        assert neg == 0

    def test_multiple_positive_patterns(self):
        """여러 긍정 패턴: 깨끗하고 친절하고 만족했다 → pos >= 2"""
        pos, neg = count_sentiment_matches("깨끗하고 친절하고 만족했다")
        assert pos >= 2

    def test_multiple_negative_patterns(self):
        """여러 부정 패턴: 더럽고 냄새나고 불편했다 → neg >= 2"""
        pos, neg = count_sentiment_matches("더럽고 냄새나고 불편했다")
        assert neg >= 2

    def test_returns_tuple_of_ints(self):
        """반환 타입이 (int, int) 튜플인지 확인"""
        result = count_sentiment_matches("테스트")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], int)
        assert isinstance(result[1], int)

    def test_empty_text_returns_zeros(self):
        """빈 문자열 → (0, 0)"""
        pos, neg = count_sentiment_matches("")
        assert pos == 0
        assert neg == 0

    def test_청결_positive_match(self):
        """'청결하게 관리된 차량' → pos >= 1"""
        pos, neg = count_sentiment_matches("청결하게 관리된 차량")
        assert pos >= 1


# =============================================================================
# detect_keyword_sentiment
# =============================================================================


class TestDetectKeywordSentiment:
    """detect_keyword_sentiment(keyword) -> str"""

    def test_친절_is_positive(self):
        """'친절' → positive"""
        assert detect_keyword_sentiment("친절") == "positive"

    def test_청결_is_positive(self):
        """'청결' → positive"""
        assert detect_keyword_sentiment("청결") == "positive"

    def test_추천_is_positive(self):
        """'추천' → positive"""
        assert detect_keyword_sentiment("추천") == "positive"

    def test_불친절_is_negative(self):
        """'불친절' → negative"""
        assert detect_keyword_sentiment("불친절") == "negative"

    def test_더러움_is_negative(self):
        """'더러움' → negative"""
        assert detect_keyword_sentiment("더러움") == "negative"

    def test_비쌈_is_negative(self):
        """'비싸' → negative"""
        assert detect_keyword_sentiment("비싸") == "negative"

    def test_배차_is_neutral(self):
        """'배차' → neutral (단독 사용시)"""
        assert detect_keyword_sentiment("배차") == "neutral"

    def test_empty_keyword_is_neutral(self):
        """빈 문자열 → neutral"""
        assert detect_keyword_sentiment("") == "neutral"

    def test_만족_is_positive(self):
        """'만족' → positive"""
        assert detect_keyword_sentiment("만족") == "positive"

    def test_최악_is_negative(self):
        """'최악' → negative"""
        assert detect_keyword_sentiment("최악") == "negative"

    def test_returns_string(self):
        """반환값이 문자열인지 확인"""
        result = detect_keyword_sentiment("친절")
        assert isinstance(result, str)
        assert result in ("positive", "negative", "neutral")

    def test_편안_is_positive(self):
        """'편안' → positive (긍정 예외 패턴)"""
        result = detect_keyword_sentiment("편안")
        assert result == "positive"


# =============================================================================
# detect_keyword_sentiment_with_context
# =============================================================================


class TestDetectKeywordSentimentWithContext:
    """detect_keyword_sentiment_with_context(keyword, context) -> str"""

    def test_positive_keyword_in_negative_context(self):
        """'친절' + '친절하지 않았다' → negative"""
        result = detect_keyword_sentiment_with_context("친절", "친절하지 않았다")
        assert result == "negative"

    def test_negative_keyword_with_double_negation(self):
        """'불편' + '불편하지 않았습니다' → positive (이중부정)"""
        result = detect_keyword_sentiment_with_context("불편", "불편하지 않았습니다")
        assert result == "positive"

    def test_keyword_not_in_context_returns_base(self):
        """키워드가 문맥에 없으면 기본 감정 반환"""
        result = detect_keyword_sentiment_with_context("친절", "전혀 다른 텍스트입니다")
        assert result == "positive"

    def test_empty_context_returns_base_sentiment(self):
        """빈 문맥 → 기본 감정 반환"""
        result = detect_keyword_sentiment_with_context("친절", "")
        assert result == "positive"

    def test_negative_keyword_in_plain_context(self):
        """'불친절' + '불친절한 서비스' → negative"""
        result = detect_keyword_sentiment_with_context("불친절", "불친절한 서비스")
        assert result == "negative"

    def test_positive_keyword_in_positive_context(self):
        """'친절' + '정말 친절한 직원이었습니다' → positive"""
        result = detect_keyword_sentiment_with_context("친절", "정말 친절한 직원이었습니다")
        assert result == "positive"

    def test_adversative_context_selects_correct_clause(self):
        """역접 문맥: '친절하지만 더러웠다' + keyword '더러움'
        → '더럽' 패턴이 keyword 뒤 절에 있으므로 negative"""
        result = detect_keyword_sentiment_with_context("더러움", "친절하지만 더러웠다")
        assert result == "negative"

    def test_negation_prefix_only_returns_negative(self):
        """'친절'이 '불친절한 서비스'에서 불친절 안에서만 등장 → negative"""
        result = detect_keyword_sentiment_with_context("친절", "불친절한 서비스")
        assert result == "negative"


# =============================================================================
# _is_negation_prefixed_only
# =============================================================================


class TestIsNegationPrefixedOnly:
    """_is_negation_prefixed_only(keyword, context) -> bool"""

    def test_불친절에서_친절은_True(self):
        """'친절' in '불친절한 서비스' → True (부정 접두사 안에서만)"""
        assert _is_negation_prefixed_only("친절", "불친절한 서비스") is True

    def test_불편에서_편은_True(self):
        """'편' in '불편하지 않았다' → True"""
        assert _is_negation_prefixed_only("편", "불편하지 않았다") is True

    def test_독립적_친절은_False(self):
        """'친절' in '친절한 서비스' → False (부정 접두사 없음)"""
        assert _is_negation_prefixed_only("친절", "친절한 서비스") is False

    def test_부정과_독립이_혼재하면_False(self):
        """'친절' in '불친절하지만 친절한 부분도 있다' → False (독립 친절 존재)"""
        assert _is_negation_prefixed_only("친절", "불친절하지만 친절한 부분도 있다") is False

    def test_비위생에서_위생은_True(self):
        """'위생' in '비위생적인 차량' → True"""
        assert _is_negation_prefixed_only("위생", "비위생적인 차량") is True

    def test_무성의에서_성의는_True(self):
        """'성의' in '무성의한 태도' → True"""
        assert _is_negation_prefixed_only("성의", "무성의한 태도") is True

    def test_keyword_not_in_context_returns_False(self):
        """키워드가 문맥에 전혀 없으면 → False"""
        assert _is_negation_prefixed_only("친절", "전혀 다른 텍스트") is False


# =============================================================================
# _trim_window_by_adversative
# =============================================================================


class TestTrimWindowByAdversative:
    """_trim_window_by_adversative(window, kw_pos) -> str"""

    def test_keyword_before_adversative_returns_prefix(self):
        """키워드가 역접 앞: '친절하지만 더러웠다', kw_pos=0 → '친절하'"""
        window = "친절하지만 더러웠다"
        # '친절' 위치 = 0, '지만' 시작 = 3
        result = _trim_window_by_adversative(window, 0)
        assert "더러웠" not in result
        assert "친절" in result

    def test_keyword_after_adversative_returns_suffix(self):
        """키워드가 역접 뒤: '친절하지만 더러웠다', kw_pos after '지만' → '더러웠다'"""
        window = "친절하지만 더러웠다"
        # '더러웠다' 시작 위치는 7 이후
        kw_pos = window.index("더러웠다")
        result = _trim_window_by_adversative(window, kw_pos)
        assert "친절" not in result
        assert "더러웠다" in result

    def test_no_adversative_returns_full_window(self):
        """역접 없으면 전체 윈도우 반환"""
        window = "친절하고 깨끗한 차량이었습니다"
        result = _trim_window_by_adversative(window, 0)
        assert result == window

    def test_empty_window_returns_empty(self):
        """빈 윈도우 → 빈 문자열 반환"""
        result = _trim_window_by_adversative("", 0)
        assert result == ""

    def test_multiple_adversatives_uses_closest(self):
        """여러 역접 중 kw_pos에 가장 가까운 것 선택"""
        # '친절하지만 더럽지만 가격은 좋아요'
        # kw_pos = '좋아요' 위치 (맨 뒤) → 가장 가까운 역접은 두 번째 '지만'
        window = "친절하지만 더럽지만 가격은 좋아요"
        kw_pos = window.index("좋아요")
        result = _trim_window_by_adversative(window, kw_pos)
        # 두 번째 '지만' 이후인 ' 가격은 좋아요'가 반환되어야 함
        assert "친절" not in result
        assert "좋아요" in result

    def test_다만_adversative_splits_window(self):
        """'다만' 역접도 절 분리에 사용"""
        window = "친절했다만 불편했다"
        kw_pos = window.index("불편")
        result = _trim_window_by_adversative(window, kw_pos)
        assert "친절" not in result
        assert "불편" in result

    def test_keyword_exactly_at_adversative_boundary(self):
        """kw_pos가 역접 직후인 경우 뒷 절 반환"""
        window = "문제없지만 조금 불편했다"
        kw_pos = window.index("불편")
        result = _trim_window_by_adversative(window, kw_pos)
        assert "문제없" not in result
