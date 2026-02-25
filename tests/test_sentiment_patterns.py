r"""Phase 2 회귀 테스트: 패턴 변경 전 현재 동작 캡처

대상:
- Task 2-1: 없지\s*않 NEGATIVE→DOUBLE_NEGATION 이동
- Task 2-2: 그다지...않 패턴 추가
- Task 2-3: absa.py strong_negative → patterns.py 통합
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))


# ============================================================
# Task 2-1 대상: 없지\s*않 패턴 위치
# ============================================================


class TestNegPatternLocation:
    """없지 않 패턴의 현재 위치(NEGATIVE) 검증 — 이동 후 달라질 동작"""

    def test_없지않_detected_as_negative_match(self):
        """현재: '없지 않' → NEGATIVE_PATTERNS에서 부정 매칭"""
        from domain.analysis.sentiment_core import count_sentiment_matches

        pos, neg = count_sentiment_matches("없지 않은 서비스")
        assert neg >= 1, "현재 '없지 않'은 NEGATIVE에서 매칭되어야 함"

    def test_없지않_now_in_double_negation(self):
        """수정 후: '없지 않' → DOUBLE_NEGATION에 등록 (이중부정=긍정)"""
        from domain.analysis.sentiment_core import check_double_negation

        result = check_double_negation("없지 않은 서비스")
        assert result is True, "'없지 않'은 이중부정으로 긍정 처리"

    def test_불편함이_없지않았다_double_neg_via_broad_pattern(self):
        """현재: '불편함이 없지 않았다' → 기존 광범위 패턴으로 이중부정 매칭"""
        from domain.analysis.sentiment_core import check_double_negation

        result = check_double_negation("불편함이 없지 않았다")
        # "불편...않" 광범위 패턴이 부분 매칭
        assert result is True


# ============================================================
# Task 2-2 대상: 그다지...않 미커버
# ============================================================


class TestMissingDoubleNegation:
    """현재 커버되지 않는 이중부정 패턴 확인"""

    def test_그다지_좋지않_now_covered(self):
        """수정 후: '그다지 좋지 않았다' → 이중부정 매칭 (긍정)"""
        from domain.analysis.sentiment_core import check_double_negation

        result = check_double_negation("그다지 좋지 않았다")
        assert result is True, "'그다지...않' 패턴 추가됨"

    def test_그다지_나쁘지않_covered_via_existing(self):
        """'그다지 나쁘지 않았다' → '나쁘지.{0,5}않'으로 이미 매칭"""
        from domain.analysis.sentiment_core import check_double_negation

        result = check_double_negation("그다지 나쁘지 않았다")
        assert result is True, "'나쁘지.{0,5}않' 패턴으로 매칭"

    def test_별로였다_stays_negative(self):
        """'별로였다' → 부정 유지 (오탐 방지 확인)"""
        from domain.analysis.sentiment_core import count_sentiment_matches

        pos, neg = count_sentiment_matches("별로였다")
        assert neg >= 1, "'별로' 패턴은 부정으로 유지"


# ============================================================
# Task 2-3 대상: absa.py strong_negative 하드코딩
# ============================================================


class TestStrongNegativePatterns:
    """absa.py _determine_sentiment()의 strong_negative 동작 검증"""

    def _make_absa(self):
        from domain.analysis.absa import RuleBasedABSA

        return RuleBasedABSA()

    def test_불친절_detected_negative(self):
        """'불친절한 서비스' → negative"""
        absa = self._make_absa()
        sentiment, confidence = absa._determine_sentiment("불친절한 서비스")
        assert sentiment == "negative"
        assert confidence >= 0.7

    def test_최악_detected_negative(self):
        """'최악이었다' → negative"""
        absa = self._make_absa()
        sentiment, confidence = absa._determine_sentiment("최악이었다")
        assert sentiment == "negative"

    def test_실망_detected_negative(self):
        """'정말 실망했습니다' → negative"""
        absa = self._make_absa()
        sentiment, confidence = absa._determine_sentiment("정말 실망했습니다")
        assert sentiment == "negative"


# ============================================================
# 기존 DOUBLE_NEGATION 정상 동작 확인
# ============================================================


class TestExistingDoubleNegation:
    """기존 이중부정 패턴이 정상 작동하는지 확인"""

    def test_나쁘지않_positive(self):
        """'나쁘지 않았다' → 이중부정 → positive"""
        from domain.analysis.sentiment_core import check_double_negation

        assert check_double_negation("나쁘지 않았다") is True

    def test_불편하지않_positive(self):
        """'불편하지 않았어요' → 이중부정 → positive"""
        from domain.analysis.sentiment_core import check_double_negation

        assert check_double_negation("불편하지 않았어요") is True

    def test_별다른_없_positive(self):
        """'별다른 문제 없었어요' → 이중부정"""
        from domain.analysis.sentiment_core import check_double_negation

        assert check_double_negation("별다른 문제 없었어요") is True
