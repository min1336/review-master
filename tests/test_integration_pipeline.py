"""통합 테스트 (Integration Testing)

Chunker → ABSA → HybridClassifier 전체 파이프라인
실제 한국어 리뷰를 입력하여 end-to-end 동작 검증
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

os.environ.setdefault("LIGHTWEIGHT_MODE", "true")

from domain.analysis.absa import RuleBasedABSA
from domain.analysis.chunker import ClauseChunker
from domain.analysis.hybrid_classifier import HybridClassifier
from domain.analysis.patterns import TAG_REGISTRY


@pytest.fixture(scope="module")
def classifier():
    return HybridClassifier(embedding_enabled=False)


@pytest.fixture(scope="module")
def absa():
    return RuleBasedABSA()


# ── 실제 리뷰 End-to-End ─────────────────────────────


class TestRealReviewPipeline:
    """실제 렌트카 리뷰 스타일의 텍스트로 전체 파이프라인 검증"""

    REVIEWS = [
        # (리뷰, 기대 카테고리 포함, 기대 감정)
        (
            "직원분이 정말 친절하셨고 차량도 깨끗해서 만족합니다",
            ["직원친절", "청결"],
            "positive",
        ),
        (
            "가격은 저렴한데 차가 너무 더러웠어요. 담배냄새가 심했습니다",
            ["가격", "청결"],
            "mixed",
        ),
        (
            "배차가 늦어서 한참을 기다렸습니다. 직원도 불친절했어요",
            ["배달/배차", "직원친절"],
            "negative",
        ),
        (
            "걱정했는데 괜한 걱정이었어요. 깨끗하고 친절해서 감사합니다",
            ["청결", "직원친절"],
            "positive",
        ),
    ]

    @pytest.mark.parametrize("review,expected_aspects,expected_sentiment", REVIEWS)
    def test_pipeline_detects_aspects(
        self, classifier, review, expected_aspects, expected_sentiment
    ):
        result = classifier.classify_review(review)
        detected = set(result.keys())
        for expected in expected_aspects:
            assert expected in detected, (
                f"'{expected}' not in {detected} for: {review}"
            )

    @pytest.mark.parametrize("review,expected_aspects,expected_sentiment", REVIEWS)
    def test_pipeline_overall_sentiment(
        self, classifier, review, expected_aspects, expected_sentiment
    ):
        summary = classifier.get_review_summary(review)
        if expected_sentiment == "positive":
            assert summary["overall_sentiment"] in ("positive", "mixed")
        elif expected_sentiment == "negative":
            assert summary["overall_sentiment"] in ("negative", "mixed")
        # mixed는 어떤 결과든 허용


# ── Chunker → ABSA 연동 ──────────────────────────────


class TestChunkerAbsaIntegration:
    def test_multi_clause_produces_multi_aspect(self, absa):
        review = "직원이 친절했어요. 하지만 차가 더러웠고, 가격도 비쌌어요"
        results = absa.analyze(review)
        aspects = {r["aspect"] for r in results}
        assert len(aspects) >= 2

    def test_single_clause_single_aspect(self, absa):
        review = "직원이 정말 친절했어요"
        results = absa.analyze(review)
        aspects = {r["aspect"] for r in results}
        assert "직원친절" in aspects

    def test_chunker_consistency(self):
        """같은 입력에 같은 출력 (결정론적)"""
        chunker = ClauseChunker(use_punctuation=True)
        review = "친절했지만 차가 더러웠어요. 가격은 저렴해요"
        result1 = chunker.chunk(review)
        result2 = chunker.chunk(review)
        assert result1 == result2


# ── classify_review 출력 → TAG_REGISTRY 정합성 ───────


class TestOutputRegistryConsistency:
    """classify_review 결과의 태그가 TAG_REGISTRY에 존재하는지"""

    SAMPLE_REVIEWS = [
        "친절한 직원, 깨끗한 차, 저렴한 가격!",
        "불친절하고 더러운 차량, 바가지 요금",
        "배차가 빠르고 반납도 편했어요",
        "보험 처리가 신속했습니다",
        "주유비 부담 없이 잘 탔어요",
    ]

    @pytest.mark.parametrize("review", SAMPLE_REVIEWS)
    def test_all_aspects_in_registry(self, classifier, review):
        result = classifier.classify_review(review)
        valid_categories = set(TAG_REGISTRY.keys())
        for aspect in result.keys():
            assert aspect in valid_categories, (
                f"'{aspect}' not in TAG_REGISTRY for: {review}"
            )


# ── ABSA → classify_review 호환성 ────────────────────


class TestAbsaClassifierConsistency:
    """ABSA 직접 호출과 HybridClassifier 경유 결과 비교"""

    def test_absa_and_classifier_detect_same_aspects(self, absa, classifier):
        review = "직원이 친절하고 차가 깨끗해요"
        absa_result = absa.classify_review(review)
        hybrid_result = classifier.classify_review(review)

        # HybridClassifier는 ABSA 결과를 포함해야 함
        for aspect in absa_result:
            assert aspect in hybrid_result, (
                f"ABSA detected '{aspect}' but HybridClassifier missed it"
            )
