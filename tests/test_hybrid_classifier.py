"""HybridClassifier 단위 테스트 (경량 모드, 임베딩 비활성화)

규칙 기반 태그 매핑, ABSA 연동, classify_review/get_review_summary 검증
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

os.environ.setdefault("LIGHTWEIGHT_MODE", "true")

from domain.analysis.hybrid_classifier import HybridClassifier


@pytest.fixture(scope="module")
def classifier():
    return HybridClassifier(embedding_enabled=False)


# ── _check_rule_based_mapping ─────────────────────────


class TestRuleBasedMapping:
    def test_exact_match(self, classifier):
        result = classifier._check_rule_based_mapping("친절")
        assert result is not None
        assert result[0] == "친절"
        assert result[1] == 1.0

    def test_stem_match(self, classifier):
        result = classifier._check_rule_based_mapping("친절한")
        assert result is not None
        assert result[0] == "친절"

    def test_substring_match(self, classifier):
        result = classifier._check_rule_based_mapping("불친절해요")
        assert result is not None
        assert result[0] == "친절"

    def test_no_match_returns_none(self, classifier):
        result = classifier._check_rule_based_mapping("아스팔트")
        assert result is None

    def test_empty_keyword(self, classifier):
        result = classifier._check_rule_based_mapping("")
        assert result is None


# ── _classify_keyword (경량 모드) ─────────────────────


class TestClassifyKeywordLightweight:
    def test_rule_mapped_keyword(self, classifier):
        tag, score = classifier._classify_keyword("에어컨")
        assert tag == "옵션"
        assert score == 1.0

    def test_generic_keyword_returns_etc(self, classifier):
        tag, score = classifier._classify_keyword("상태")
        assert tag == "기타"

    def test_general_positive_returns_etc(self, classifier):
        tag, score = classifier._classify_keyword("좋아요")
        assert tag == "기타"

    def test_empty_keyword(self, classifier):
        tag, score = classifier._classify_keyword("")
        assert tag == "기타"
        assert score == 0.0

    def test_none_safe(self, classifier):
        tag, score = classifier._classify_keyword(None)
        assert tag == "기타"


# ── classify_review ───────────────────────────────────


class TestClassifyReview:
    def test_positive_service(self, classifier):
        result = classifier.classify_review("직원이 정말 친절했어요")
        assert "직원친절" in result
        assert len(result["직원친절"]["positive"]) > 0

    def test_negative_cleanliness(self, classifier):
        result = classifier.classify_review("차가 너무 더러웠어요 냄새 심해요")
        assert "청결" in result
        assert len(result["청결"]["negative"]) > 0

    def test_mixed_review_multiple_aspects(self, classifier):
        result = classifier.classify_review(
            "직원은 친절한데 차가 지저분하고 가격도 비싸요"
        )
        assert len(result) >= 2

    def test_review_with_keywords(self, classifier):
        result = classifier.classify_review(
            "직원이 친절하고 차가 깨끗했어요",
            keywords=["친절", "깨끗"],
        )
        assert "직원친절" in result or "청결" in result

    def test_empty_review(self, classifier):
        result = classifier.classify_review("")
        assert result == {}

    def test_short_review(self, classifier):
        result = classifier.classify_review("좋아요")
        # 너무 짧아도 크래시 없이 빈 결과 또는 분류 결과 반환
        assert isinstance(result, dict)

    def test_output_structure_contract(self, classifier):
        """Contract: 모든 태그의 감정은 positive/negative/neutral 키를 가짐"""
        result = classifier.classify_review("친절하고 깨끗하지만 비싸요")
        for tag, sentiments in result.items():
            assert "positive" in sentiments
            assert "negative" in sentiments
            assert "neutral" in sentiments
            assert isinstance(sentiments["positive"], list)
            assert isinstance(sentiments["negative"], list)
            assert isinstance(sentiments["neutral"], list)

    def test_max_keywords_per_category_cap(self, classifier):
        """키워드 수 상한(3) 적용 확인"""
        # 같은 카테고리에 많은 키워드가 매핑되더라도 3개까지만
        result = classifier.classify_review(
            "친절하고 상냥하고 배려깊고 미소짓고 감사합니다 인사 안내 설명"
        )
        for tag, sentiments in result.items():
            for sent_type in ("positive", "negative", "neutral"):
                assert len(sentiments[sent_type]) <= 3


# ── get_review_summary ────────────────────────────────


class TestGetReviewSummary:
    def test_summary_structure(self, classifier):
        summary = classifier.get_review_summary("직원이 친절하고 차가 깨끗해요")
        assert "aspects" in summary
        assert "overall_sentiment" in summary
        assert "positive_aspects" in summary
        assert "negative_aspects" in summary
        assert "details" in summary

    def test_positive_overall(self, classifier):
        summary = classifier.get_review_summary("직원이 정말 친절했어요 최고!")
        assert summary["overall_sentiment"] in ("positive", "mixed")

    def test_negative_overall(self, classifier):
        summary = classifier.get_review_summary("더럽고 불친절하고 비싸고 최악")
        assert summary["overall_sentiment"] in ("negative", "mixed")

    def test_mixed_overall(self, classifier):
        summary = classifier.get_review_summary(
            "직원은 친절한데 차가 너무 더러웠어요"
        )
        assert summary["overall_sentiment"] in ("mixed", "positive", "negative")


# ── classify_keywords (배치) ──────────────────────────


class TestClassifyKeywords:
    def test_batch_classification(self, classifier):
        results = classifier.classify_keywords(["친절", "더러운", "에어컨"])
        assert len(results) == 3
        # 각 항목은 (tag, score, sentiment) 튜플
        for tag, score, sentiment in results:
            assert isinstance(tag, str)
            assert isinstance(score, float)
            assert sentiment in ("positive", "negative", "neutral")

    def test_empty_list(self, classifier):
        results = classifier.classify_keywords([])
        assert results == []

    def test_context_classification(self, classifier):
        results = classifier.classify_keywords_with_context(
            ["친절"],
            "직원이 불친절했어요",
        )
        assert len(results) == 1
        _, _, sentiment = results[0]
        assert sentiment == "negative"
