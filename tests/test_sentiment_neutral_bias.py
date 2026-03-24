"""Task 2: 감정분석 중립 편향 수정 TDD 테스트

수정 사항:
1. preprocessor: 중립 오버라이드 임계값 3.0 → 4.0
2. preprocessor: _analyze_by_rating 3.5+ 긍정 구간 추가
3. sentiment_utils: "mixed" 감정 다수결 해소
4. realtime_pipeline: _analyze_by_rating 3.5+ 동기화
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))


# ============================================================
# 공통 헬퍼 (모듈 레벨)
# ============================================================


def _make_preprocessor_with_text_sentiment(
    text_sentiment: str, confidence: float = 0.8
):
    """preprocessor + 실제 UnifiedSentimentAnalyzer (sub-components만 모킹)"""
    from domain.pipeline.steps.preprocessor import ReviewPreprocessor
    from domain.analysis.sentiment_utils import UnifiedSentimentAnalyzer

    pp = ReviewPreprocessor.__new__(ReviewPreprocessor)
    pp._kiwi = None
    pp._hybrid_classifier = None

    analyzer = UnifiedSentimentAnalyzer(lazy_load=True)

    mock_absa = MagicMock()
    mock_absa.determine_text_sentiment.return_value = (text_sentiment, confidence)
    analyzer._absa = mock_absa

    mock_hybrid = MagicMock()
    if text_sentiment == "positive":
        aspects = {"positive_aspects": ["좋음"], "negative_aspects": []}
    elif text_sentiment == "negative":
        aspects = {"positive_aspects": [], "negative_aspects": ["나쁨"]}
    else:
        aspects = {"positive_aspects": [], "negative_aspects": []}
    mock_hybrid.get_review_summary.return_value = {
        "overall_sentiment": text_sentiment,
        **aspects,
    }
    analyzer._hybrid = mock_hybrid

    pp._sentiment_analyzer = analyzer
    return pp


# ============================================================
# Test 1: preprocessor 중립 오버라이드 임계값 (3.0→4.0)
# ============================================================


class TestPreprocessorNeutralOverride:
    """negative 텍스트 + 별점 조합의 중립 오버라이드 동작 검증

    preprocessor는 UnifiedSentimentAnalyzer.analyze_with_ratings()에 위임.
    _absa와 _hybrid만 모킹하여 텍스트 감정을 제어하고, 별점 통합 로직은 실제 실행.
    """

    def test_negative_text_with_rating_3_stays_negative(self):
        """별점 3.0 + 부정 텍스트 → 부정 유지"""
        pp = _make_preprocessor_with_text_sentiment("negative", 0.8)

        sentiment, _ = pp._analyze_sentiment_with_ratings(
            text="서비스가 너무 불친절했어요",
            keywords=["불친절"],
            rating_service=3.0,
            rating_car=3.0,
            rating_convenience=3.0,
        )

        assert sentiment == "negative", (
            f"별점 3.0 + 부정 텍스트는 negative여야 함, got: {sentiment}"
        )

    def test_negative_text_with_rating_3_5_stays_negative(self):
        """별점 3.5 + 부정 텍스트 → 부정 유지"""
        pp = _make_preprocessor_with_text_sentiment("negative", 0.8)

        sentiment, _ = pp._analyze_sentiment_with_ratings(
            text="차가 너무 더러웠습니다",
            keywords=["더러움"],
            rating_service=3.5,
            rating_car=3.5,
            rating_convenience=3.5,
        )

        assert sentiment == "negative"

    def test_negative_text_with_all_high_ratings_becomes_neutral(self):
        """별점 모두 4.0+ + 부정 텍스트 → neutral (정당한 오버라이드)"""
        pp = _make_preprocessor_with_text_sentiment("negative", 0.7)

        sentiment, _ = pp._analyze_sentiment_with_ratings(
            text="좀 아쉬운 부분이 있었어요",
            keywords=["아쉬움"],
            rating_service=4.5,
            rating_car=4.0,
            rating_convenience=5.0,
        )

        assert sentiment == "neutral"

    def test_positive_text_passes_through(self):
        """긍정 텍스트 + 보통 별점 → positive 그대로 유지"""
        pp = _make_preprocessor_with_text_sentiment("positive", 0.9)

        sentiment, _ = pp._analyze_sentiment_with_ratings(
            text="정말 친절하고 좋았습니다",
            keywords=["친절"],
            rating_service=3.5,
            rating_car=3.5,
            rating_convenience=3.5,
        )

        assert sentiment == "positive"

    def test_any_low_rating_with_high_avg_becomes_neutral(self):
        """별점 하나 3.0 미만이지만 평균 >= 3.5 → neutral (텍스트 무시하지 않음)"""
        pp = _make_preprocessor_with_text_sentiment("positive", 0.9)

        sentiment, _ = pp._analyze_sentiment_with_ratings(
            text="좋았습니다",
            keywords=["좋음"],
            rating_service=5.0,
            rating_car=2.5,
            rating_convenience=4.0,
        )

        assert sentiment == "neutral"


# ============================================================
# Test 1-B: 통합 경로 단일화 행동 변경 검증
# ============================================================


class TestUnifiedPathBehaviorChange:
    """preprocessor → UnifiedSentimentAnalyzer 위임 후 행동 변경 검증

    analyzer의 _integrate_with_ratings() 규칙:
    - Rule 3: text=negative + avg>=4.0 → neutral (preprocessor는 all>=4.0이었음)
    - Rule 4: text=positive + avg<3.5 → neutral (preprocessor에 없던 규칙)
    """



    def test_positive_text_low_avg_becomes_neutral(self):
        """행동 변경: text=positive + avg<3.5 → neutral (Rule 4)"""
        pp = _make_preprocessor_with_text_sentiment("positive", 0.8)

        sentiment, _ = pp._analyze_sentiment_with_ratings(
            text="정말 친절했어요",
            keywords=["친절"],
            rating_service=3.0,
            rating_car=3.0,
            rating_convenience=3.0,
        )

        assert sentiment == "neutral", (
            f"text=positive + avg<3.5 → neutral이어야 함, got: {sentiment}"
        )

    def test_negative_text_high_avg_not_all_becomes_neutral(self):
        """행동 변경: text=negative + avg≥4.0 (not all≥4.0) → neutral (Rule 3, avg 기준)"""
        pp = _make_preprocessor_with_text_sentiment("negative", 0.8)

        sentiment, _ = pp._analyze_sentiment_with_ratings(
            text="좀 아쉬운 점이 있었어요",
            keywords=["아쉬움"],
            rating_service=3.5,
            rating_car=5.0,
            rating_convenience=4.0,
        )

        # avg = 4.17 ≥ 4.0 → neutral (이전: not all≥4.0이라 negative 유지됨)
        assert sentiment == "neutral", (
            f"text=negative + avg≥4.0 → neutral이어야 함, got: {sentiment}"
        )

    def test_positive_text_at_boundary_stays_positive(self):
        """경계: text=positive + avg=3.5 → positive 유지 (Rule 4 미적용)"""
        pp = _make_preprocessor_with_text_sentiment("positive", 0.85)

        sentiment, _ = pp._analyze_sentiment_with_ratings(
            text="정말 좋았습니다",
            keywords=["좋음"],
            rating_service=3.5,
            rating_car=3.5,
            rating_convenience=3.5,
        )

        assert sentiment == "positive", (
            f"avg=3.5 경계에서 positive 유지되어야 함, got: {sentiment}"
        )


# ============================================================
# Test 2: _analyze_by_rating 3.5+ 구간
# ============================================================


class TestAnalyzeByRating:
    """별점만으로 감정 판단 시 3.5+ 구간 검증"""

    def _make_preprocessor(self):
        from domain.pipeline.steps.preprocessor import ReviewPreprocessor

        pp = ReviewPreprocessor.__new__(ReviewPreprocessor)
        pp._kiwi = None
        pp._sentiment_analyzer = None
        pp._hybrid_classifier = None
        return pp

    def test_avg_4_0_is_positive(self):
        """평균 4.0+ → positive (0.8)"""
        pp = self._make_preprocessor()
        sentiment, confidence = pp._analyze_by_rating(4.5, 4.0, 4.0)
        assert sentiment == "positive"
        assert confidence == 0.8

    def test_avg_3_5_is_positive(self):
        """평균 3.5~3.9 → positive (0.65) — 새 구간"""
        pp = self._make_preprocessor()
        sentiment, confidence = pp._analyze_by_rating(3.5, 3.5, 3.5)
        assert sentiment == "positive"
        assert confidence == 0.65

    def test_avg_3_7_is_positive(self):
        """평균 3.7 → positive (0.65) — 새 구간"""
        pp = self._make_preprocessor()
        sentiment, confidence = pp._analyze_by_rating(3.5, 4.0, 3.5)
        assert sentiment == "positive"
        assert confidence >= 0.65

    def test_avg_3_2_is_neutral(self):
        """평균 3.0~3.4 → neutral"""
        pp = self._make_preprocessor()
        sentiment, confidence = pp._analyze_by_rating(3.0, 3.5, 3.0)
        # 3.0+3.5+3.0 = 9.5/3 = 3.17 → neutral
        assert sentiment == "neutral", f"평균 3.17은 neutral이어야 함, got: {sentiment}"
        assert confidence == 0.5

    def test_avg_below_3_is_negative(self):
        """평균 3.0 미만 → negative"""
        pp = self._make_preprocessor()
        sentiment, _ = pp._analyze_by_rating(2.0, 2.5, 2.0)
        assert sentiment == "negative"

    def test_no_ratings_is_neutral(self):
        """별점 없음 → neutral"""
        pp = self._make_preprocessor()
        sentiment, _ = pp._analyze_by_rating(None, None, None)
        assert sentiment == "neutral"


# ============================================================
# Test 3: sentiment_utils "mixed" 해소
# ============================================================


class TestMixedSentimentResolution:
    """HybridClassifier의 'mixed' 감정을 다수결로 해소하는지 검증"""

    def _make_analyzer(self):
        from domain.analysis.sentiment_utils import UnifiedSentimentAnalyzer

        analyzer = UnifiedSentimentAnalyzer(lazy_load=True)
        return analyzer

    def test_mixed_with_more_positive_becomes_positive(self):
        """mixed + positive 3개 > negative 1개 → positive"""
        analyzer = self._make_analyzer()
        mock_hybrid = MagicMock()
        mock_hybrid.get_review_summary.return_value = {
            "overall_sentiment": "mixed",
            "positive_aspects": ["친절", "청결", "빠른출고"],
            "negative_aspects": ["가격"],
        }
        analyzer._hybrid = mock_hybrid

        result = analyzer._analyze_hybrid("테스트 텍스트", ["친절"])

        assert result["sentiment"] == "positive", (
            f"positive 3 > negative 1이면 positive여야 함, got: {result['sentiment']}"
        )

    def test_mixed_with_more_negative_becomes_negative(self):
        """mixed + negative 3개 > positive 1개 → negative"""
        analyzer = self._make_analyzer()
        mock_hybrid = MagicMock()
        mock_hybrid.get_review_summary.return_value = {
            "overall_sentiment": "mixed",
            "positive_aspects": ["친절"],
            "negative_aspects": ["더러움", "비쌈", "불친절"],
        }
        analyzer._hybrid = mock_hybrid

        result = analyzer._analyze_hybrid("테스트 텍스트", [])

        assert result["sentiment"] == "negative"

    def test_mixed_with_equal_becomes_neutral(self):
        """mixed + positive == negative → neutral"""
        analyzer = self._make_analyzer()
        mock_hybrid = MagicMock()
        mock_hybrid.get_review_summary.return_value = {
            "overall_sentiment": "mixed",
            "positive_aspects": ["친절", "청결"],
            "negative_aspects": ["비쌈", "느림"],
        }
        analyzer._hybrid = mock_hybrid

        result = analyzer._analyze_hybrid("테스트 텍스트", [])

        assert result["sentiment"] == "neutral"

    def test_standard_positive_unchanged(self):
        """정상 positive → 변경 없음"""
        analyzer = self._make_analyzer()
        mock_hybrid = MagicMock()
        mock_hybrid.get_review_summary.return_value = {
            "overall_sentiment": "positive",
            "positive_aspects": ["친절", "청결"],
            "negative_aspects": [],
        }
        analyzer._hybrid = mock_hybrid

        result = analyzer._analyze_hybrid("좋았습니다", ["친절"])

        assert result["sentiment"] == "positive"

    def test_standard_negative_unchanged(self):
        """정상 negative → 변경 없음"""
        analyzer = self._make_analyzer()
        mock_hybrid = MagicMock()
        mock_hybrid.get_review_summary.return_value = {
            "overall_sentiment": "negative",
            "positive_aspects": [],
            "negative_aspects": ["더러움", "불친절"],
        }
        analyzer._hybrid = mock_hybrid

        result = analyzer._analyze_hybrid("최악이었습니다", [])

        assert result["sentiment"] == "negative"

    def test_unknown_sentiment_resolved(self):
        """알 수 없는 값(예: 'ambiguous') → 다수결 해소"""
        analyzer = self._make_analyzer()
        mock_hybrid = MagicMock()
        mock_hybrid.get_review_summary.return_value = {
            "overall_sentiment": "ambiguous",
            "positive_aspects": ["친절"],
            "negative_aspects": [],
        }
        analyzer._hybrid = mock_hybrid

        result = analyzer._analyze_hybrid("텍스트", [])

        assert result["sentiment"] == "positive"


# ============================================================
# Test 4: realtime_pipeline _analyze_by_rating 동기화
# ============================================================


class TestRealtimePipelineRatingTier:
    """realtime_pipeline의 _analyze_by_rating 3.5+ 구간 동기화 검증"""

    def _make_pipeline(self):
        from domain.pipeline.realtime_pipeline import RealtimePipeline

        pipeline = RealtimePipeline.__new__(RealtimePipeline)
        return pipeline

    def test_avg_3_5_is_positive(self):
        """realtime: 평균 3.5+ → positive"""
        pipeline = self._make_pipeline()
        result = pipeline._analyze_by_rating({
            "service": 3.5, "car": 3.5, "convenience": 3.5
        })
        assert result == "positive"

    def test_avg_3_8_is_positive(self):
        """realtime: 평균 3.8 → positive"""
        pipeline = self._make_pipeline()
        result = pipeline._analyze_by_rating({
            "service": 4.0, "car": 3.5, "convenience": 4.0
        })
        assert result == "positive"

    def test_avg_4_0_is_positive(self):
        """realtime: 평균 4.0+ → positive"""
        pipeline = self._make_pipeline()
        result = pipeline._analyze_by_rating({
            "service": 4.0, "car": 4.5, "convenience": 4.0
        })
        assert result == "positive"

    def test_avg_3_2_is_neutral(self):
        """realtime: 평균 3.0~3.4 → neutral"""
        pipeline = self._make_pipeline()
        result = pipeline._analyze_by_rating({
            "service": 3.0, "car": 3.0, "convenience": 3.5
        })
        # avg = 3.17 → neutral
        assert result == "neutral"

    def test_avg_below_3_is_negative(self):
        """realtime: 평균 3.0 미만 → negative"""
        pipeline = self._make_pipeline()
        result = pipeline._analyze_by_rating({
            "service": 2.0, "car": 2.5, "convenience": 2.0
        })
        assert result == "negative"


# ============================================================
# Test 5: 개별 별점 하한 검증 (별점-감정 불일치 수정)
# ============================================================


class TestIndividualRatingLowerBound:
    """개별 별점이 3.0 미만이면 avg 무관하게 positive 불가"""

    def _make_preprocessor(self):
        from domain.pipeline.steps.preprocessor import ReviewPreprocessor

        pp = ReviewPreprocessor.__new__(ReviewPreprocessor)
        pp._kiwi = None
        pp._sentiment_analyzer = None
        pp._hybrid_classifier = None
        return pp

    def _make_pipeline(self):
        from domain.pipeline.realtime_pipeline import RealtimePipeline

        pipeline = RealtimePipeline.__new__(RealtimePipeline)
        return pipeline

    def test_svc_low_car_conv_high_not_positive_preprocessor(self):
        """preprocessor: svc=0.5, car=5.0, conv=5.0 → avg=3.5이지만 positive 아님"""
        pp = self._make_preprocessor()
        sentiment, _ = pp._analyze_by_rating(0.5, 5.0, 5.0)
        assert sentiment != "positive", (
            f"개별 별점 0.5 존재 시 positive 불가, got: {sentiment}"
        )

    def test_svc_low_avg_above_3_5_becomes_neutral_preprocessor(self):
        """preprocessor: svc=2.5, car=5.0, conv=5.0 → avg=4.17 → neutral"""
        pp = self._make_preprocessor()
        sentiment, _ = pp._analyze_by_rating(2.5, 5.0, 5.0)
        assert sentiment == "neutral"

    def test_svc_low_avg_below_3_5_becomes_negative_preprocessor(self):
        """preprocessor: svc=1.0, car=3.0, conv=3.0 → avg=2.33 → negative"""
        pp = self._make_preprocessor()
        sentiment, _ = pp._analyze_by_rating(1.0, 3.0, 3.0)
        assert sentiment == "negative"

    def test_all_low_becomes_negative_preprocessor(self):
        """preprocessor: 3개 모두 <3.0 → negative"""
        pp = self._make_preprocessor()
        sentiment, _ = pp._analyze_by_rating(2.0, 2.5, 1.5)
        assert sentiment == "negative"

    def test_svc_low_car_conv_high_not_positive_realtime(self):
        """realtime: svc=0.5, car=5.0, conv=5.0 → positive 아님"""
        pipeline = self._make_pipeline()
        result = pipeline._analyze_by_rating({
            "service": 0.5, "car": 5.0, "convenience": 5.0
        })
        assert result != "positive"

    def test_svc_low_avg_above_3_5_becomes_neutral_realtime(self):
        """realtime: svc=2.5, car=5.0, conv=5.0 → neutral"""
        pipeline = self._make_pipeline()
        result = pipeline._analyze_by_rating({
            "service": 2.5, "car": 5.0, "convenience": 5.0
        })
        assert result == "neutral"

    def test_all_high_stays_positive(self):
        """모든 별점 3.0+ → 기존 로직 유지"""
        pp = self._make_preprocessor()
        sentiment, _ = pp._analyze_by_rating(4.0, 4.5, 4.0)
        assert sentiment == "positive"
