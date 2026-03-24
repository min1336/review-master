"""absa.py 단위 테스트

RuleBasedABSA: 절별 ABSA 분석, 감정 판단, 충돌 해소
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from domain.analysis.absa import RuleBasedABSA, resolve_tag_conflicts


@pytest.fixture
def absa():
    return RuleBasedABSA()


# ── resolve_tag_conflicts ─────────────────────────────


class TestResolveTagConflicts:
    def test_no_conflict(self):
        tags = {
            "직원친절": {"positive": ["친절"], "negative": [], "neutral": []},
        }
        result = resolve_tag_conflicts(tags, has_concession=False)
        assert result["직원친절"]["positive"] == ["친절"]

    def test_positive_majority_wins(self):
        tags = {
            "직원친절": {
                "positive": ["친절", "상냥"],
                "negative": ["불친절"],
                "neutral": [],
            },
        }
        result = resolve_tag_conflicts(tags, has_concession=False)
        assert result["직원친절"]["positive"] == ["친절", "상냥"]
        assert result["직원친절"]["negative"] == []

    def test_negative_majority_wins(self):
        tags = {
            "청결": {
                "positive": ["깨끗"],
                "negative": ["더러", "냄새"],
                "neutral": [],
            },
        }
        result = resolve_tag_conflicts(tags, has_concession=False)
        assert result["청결"]["negative"] == ["더러", "냄새"]
        assert result["청결"]["positive"] == []

    def test_concession_favors_positive(self):
        tags = {
            "청결": {
                "positive": ["깨끗"],
                "negative": ["걱정"],
                "neutral": [],
            },
        }
        result = resolve_tag_conflicts(tags, has_concession=True)
        assert result["청결"]["positive"] == ["깨끗"]
        assert result["청결"]["negative"] == []

    def test_concession_with_strong_negative(self):
        # 부정 근거 2개 이상이면 반전 구문이어도 다수결
        tags = {
            "청결": {
                "positive": ["깨끗"],
                "negative": ["더러", "냄새"],
                "neutral": [],
            },
        }
        result = resolve_tag_conflicts(tags, has_concession=True)
        assert result["청결"]["negative"] == ["더러", "냄새"]

    def test_empty_tags_removed(self):
        tags = {
            "가격": {"positive": [], "negative": [], "neutral": []},
        }
        result = resolve_tag_conflicts(tags, has_concession=False)
        assert "가격" not in result


# ── RuleBasedABSA.analyze ─────────────────────────────


class TestABSAAnalyze:
    def test_empty_review(self, absa):
        assert absa.analyze("") == []
        assert absa.analyze("  ") == []
        assert absa.analyze("ab") == []  # below min length

    def test_positive_service_review(self, absa):
        results = absa.analyze("직원이 정말 친절했어요")
        assert len(results) >= 1
        aspects = [r["aspect"] for r in results]
        assert "직원친절" in aspects

    def test_negative_cleanliness_review(self, absa):
        results = absa.analyze("차가 너무 더러웠어요")
        assert len(results) >= 1
        aspects = [r["aspect"] for r in results]
        assert "청결" in aspects

    def test_mixed_review(self, absa):
        results = absa.analyze("직원은 친절했지만 차가 더러웠어요")
        aspects = [r["aspect"] for r in results]
        assert "직원친절" in aspects
        assert "청결" in aspects

    def test_price_review(self, absa):
        results = absa.analyze("가격이 저렴해서 좋았어요")
        aspects = [r["aspect"] for r in results]
        assert "가격" in aspects


# ── RuleBasedABSA._determine_sentiment ────────────────


class TestDetermineSentiment:
    def test_double_negation_positive(self, absa):
        sent, conf = absa._determine_sentiment("불편한 점이 없었어요")
        assert sent == "positive"
        assert conf >= 0.9

    def test_negated_positive_is_negative(self, absa):
        sent, conf = absa._determine_sentiment("친절하지 않았어요")
        assert sent == "negative"

    def test_strong_negative_keyword(self, absa):
        sent, conf = absa._determine_sentiment("정말 불친절했어요")
        assert sent == "negative"

    def test_clear_positive(self, absa):
        sent, conf = absa._determine_sentiment("최고예요")
        assert sent == "positive"

    def test_short_positive_review(self, absa):
        sent, conf = absa._determine_sentiment("좋았습니다")
        assert sent == "positive"

    def test_neutral_when_no_signal(self, absa):
        sent, conf = absa._determine_sentiment("차량을 이용했습니다")
        assert sent == "neutral"


# ── RuleBasedABSA.classify_review ─────────────────────


class TestClassifyReview:
    def test_basic_positive(self, absa):
        result = absa.classify_review("직원이 정말 친절했어요")
        assert "직원친절" in result
        assert len(result["직원친절"]["positive"]) > 0

    def test_basic_negative(self, absa):
        result = absa.classify_review("차가 너무 더러웠어요 냄새도 심했어요")
        assert "청결" in result
        assert len(result["청결"]["negative"]) > 0

    def test_mixed_returns_both(self, absa):
        result = absa.classify_review("직원은 친절한데 차가 지저분했어요")
        assert "직원친절" in result
        assert "청결" in result

    def test_concession_review(self, absa):
        result = absa.classify_review(
            "걱정했는데 괜한 걱정이었어요 깨끗하고 친절했습니다"
        )
        # 반전 구문 → 긍정 우세
        for aspect, sentiments in result.items():
            assert len(sentiments.get("negative", [])) == 0 or \
                   len(sentiments.get("positive", [])) > 0


# ── RuleBasedABSA.determine_text_sentiment (public) ───


class TestDetermineTextSentiment:
    def test_public_api_empty(self, absa):
        sent, conf = absa.determine_text_sentiment("")
        assert sent == "neutral"
        assert conf == 0.0

    def test_public_api_positive(self, absa):
        sent, conf = absa.determine_text_sentiment("정말 좋았어요 최고!")
        assert sent == "positive"
        assert conf > 0.5
