"""Regression Testing

알려진 버그 및 엣지 케이스 재발 방지 테스트
각 테스트에 원인 이슈를 주석으로 기록
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

os.environ.setdefault("LIGHTWEIGHT_MODE", "true")

from domain.analysis.absa import RuleBasedABSA, resolve_tag_conflicts
from domain.analysis.hybrid_classifier import HybridClassifier
from domain.analysis.patterns import (
    CONCESSION_REGEX,
    resolve_tag_category,
    TAG_TO_CATEGORY,
)
from domain.analysis.sentiment_core import (
    _is_negation_prefixed_only,
    check_double_negation,
    detect_keyword_sentiment_with_context,
)
from services.sync_service import _filter_misrouted_reviews


@pytest.fixture(scope="module")
def classifier():
    return HybridClassifier(embedding_enabled=False)


@pytest.fixture(scope="module")
def absa():
    return RuleBasedABSA()


# ── 사고 처리 오분류 회귀 ─────────────────────────────
# 이슈: "안심" "처리" 등이 문맥 없이 사고 처리로 분류됨


class TestAccidentMisclassificationRegression:
    def test_ansim_without_accident_context(self, absa):
        """'안심'이 보험/사고 문맥 없이는 사고 처리로 분류되면 안 됨"""
        results = absa.analyze("안심하고 이용했어요")
        aspects = [r["aspect"] for r in results]
        assert "사고 처리" not in aspects

    def test_ansim_with_insurance_context(self, absa):
        """'안심'이 보험 문맥에서는 사고 처리로 분류되어야 함"""
        results = absa.analyze("보험이 있어서 안심했어요")
        aspects = [r["aspect"] for r in results]
        assert "사고 처리" in aspects

    def test_cheori_without_accident_context(self, absa):
        """'처리'가 사고 문맥 없이는 사고 처리로 분류되면 안 됨"""
        results = absa.analyze("처리가 빠르네요")
        aspects = [r["aspect"] for r in results]
        assert "사고 처리" not in aspects


# ── 동일 카테고리 중복 태깅 회귀 ──────────────────────
# 이슈: pos+neg 공존 시 양쪽 모두 남아 중복 계산됨


class TestDuplicateTaggingRegression:
    def test_conflict_resolved_not_both(self):
        """pos+neg 공존 시 한쪽만 남아야 함"""
        tags = {
            "직원친절": {
                "positive": ["친절"],
                "negative": ["불친절"],
                "neutral": [],
            },
        }
        result = resolve_tag_conflicts(tags, has_concession=False)
        pos = result["직원친절"]["positive"]
        neg = result["직원친절"]["negative"]
        # 둘 다 있으면 안 됨
        assert not (pos and neg), "pos+neg 모두 존재하면 안 됨"


# ── 반전 구문(CONCESSION) 인식 회귀 ──────────────────
# 이슈: "걱정했는데 괜한 걱정" 패턴이 부정으로 잘못 분류


class TestConcessionRegression:
    def test_worry_was_unnecessary(self):
        """걱정했는데 괜한 걱정 → 반전 구문 탐지"""
        assert CONCESSION_REGEX.search("걱정했는데 괜한 걱정이었어요")

    def test_worried_but_satisfied(self):
        assert CONCESSION_REGEX.search("걱정했지만 만족했어요")

    def test_concession_review_positive(self, classifier):
        result = classifier.classify_review(
            "걱정했는데 괜한 걱정이었어요 차도 깨끗하고 직원도 친절해요"
        )
        # 최소 하나의 aspect에 긍정이 있어야 함
        has_positive = any(
            sentiments.get("positive", [])
            for sentiments in result.values()
        )
        assert has_positive


# ── 이중부정 처리 회귀 ────────────────────────────────
# 이슈: "불편한 점이 없었어요" → negative로 오분류


class TestDoubleNegationRegression:
    @pytest.mark.parametrize("text", [
        "불편한 점이 없었어요",
        "문제없이 잘 이용했습니다",
        "불편하지 않았습니다",
        "나쁘지 않았어요",
        "비싸지 않아요",
        "냄새 나지 않아요",
        "부족함 없이 좋았어요",
        "부담 없이 이용했어요",
    ])
    def test_double_negation_is_positive(self, text):
        assert check_double_negation(text) is True

    def test_absa_double_negation_positive(self, absa):
        sent, conf = absa._determine_sentiment("불편한 점이 없었어요")
        assert sent == "positive"


# ── 부정 접두사 오탐 회귀 ─────────────────────────────
# 이슈: "불친절" 리뷰에서 "친절" 키워드가 긍정으로 잡힘


class TestNegationPrefixRegression:
    def test_bulchinjeol_context(self):
        """'불친절'에서 '친절'이 독립 긍정으로 잡히면 안 됨"""
        assert _is_negation_prefixed_only("친절", "직원이 불친절했어요") is True

    def test_context_sentiment_flipped(self):
        result = detect_keyword_sentiment_with_context(
            "친절", "직원이 불친절했어요"
        )
        assert result == "negative"


# ── 오배정 리뷰 필터 회귀 ─────────────────────────────
# 이슈: Athena API가 해외 리뷰를 국내 branch_id로 매핑
# 이전 버그: dominant가 해외 리뷰일 때 정상 국내 리뷰를 삭제


class TestMisroutedFilterRegression:
    def test_minority_overseas_filtered(self):
        """소수 해외 리뷰가 정상적으로 필터링"""
        reviews = [
            {"review_id": i, "branch_id": 50, "company_name": "스마트렌트카"}
            for i in range(9)
        ]
        reviews.append(
            {"review_id": 9, "branch_id": 50, "company_name": "달러렌트카"}
        )
        filtered, dropped = _filter_misrouted_reviews(reviews)
        assert dropped == 1

    def test_majority_overseas_not_filtered(self):
        """해외 리뷰가 다수여도 80% 미만이면 필터링 안 함 (오탐 방지)"""
        reviews = [
            {"review_id": 1, "branch_id": 50, "company_name": "스마트렌트카"},
            {"review_id": 2, "branch_id": 50, "company_name": "스마트렌트카"},
            {"review_id": 3, "branch_id": 50, "company_name": "스마트렌트카"},
            {"review_id": 4, "branch_id": 50, "company_name": "달러렌트카"},
            {"review_id": 5, "branch_id": 50, "company_name": "달러렌트카"},
        ]
        # 60% dominant → 80% 미달 → 필터링 안 함
        filtered, dropped = _filter_misrouted_reviews(reviews)
        assert dropped == 0


# ── 카테고리 3분할 회귀 ───────────────────────────────
# 이슈: "배달" 카테고리를 3개로 분할 후 역매핑 깨짐


class TestCategorySplitRegression:
    def test_delivery_tags_in_correct_category(self):
        assert TAG_TO_CATEGORY["딜리버리"] == "배달/배차"
        assert TAG_TO_CATEGORY["배차/시간"] == "배달/배차"

    def test_pickup_tag_in_correct_category(self):
        assert TAG_TO_CATEGORY["반납/픽업"] == "반납/픽업"

    def test_location_tags_in_correct_category(self):
        assert TAG_TO_CATEGORY["위치/접근성"] == "위치/접근성"
        assert TAG_TO_CATEGORY["공항"] == "위치/접근성"

    def test_resolve_legacy_delivery(self):
        """구 '배달' 카테고리명이 '배달/배차'로 정규화"""
        assert resolve_tag_category("딜리버리", "배달") == "배달/배차"


# ── 긍정 예외 패턴 회귀 ──────────────────────────────
# 이슈: "부담없이", "문제없이" 등이 부정으로 오분류


class TestPositiveExceptionRegression:
    @pytest.mark.parametrize("text,expected", [
        ("부담없이 이용했어요", "positive"),
        ("문제없이 잘 됐어요", "positive"),
        ("틀림없이 최고예요", "positive"),
        ("거침없이 추천합니다", "positive"),
    ])
    def test_positive_exception_detected(self, absa, text, expected):
        sent, conf = absa._determine_sentiment(text)
        assert sent == expected, f"'{text}' → {sent} (expected {expected})"
