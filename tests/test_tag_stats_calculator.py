"""TagStatsCalculator 단위 테스트"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from services.tag_stats_calculator import TagStatsCalculator

# sample data 카테고리 이름 — AFFILIATE_CATEGORIES 패치에 사용
_SAMPLE_AFFILIATE_CATEGORIES = {"서비스", "청결", "가격"}


# ============================================================
# compute_category_stats
# ============================================================


def test_compute_category_stats_basic(sample_branch_tags):
    tag_sentiments, sentiment_stats, category_stats, tag_details = (
        TagStatsCalculator.compute_category_stats(sample_branch_tags)
    )

    # tag_sentiments: 5개 태그 모두 포함
    assert len(tag_sentiments) == 5
    names = [ts["name"] for ts in tag_sentiments]
    assert "친절한 직원" in names
    assert "비싼 가격" in names

    # sentiment_stats 합계 검증
    # pos: 80+60+5+40+2=187, neg: 5+20+50+3+30=108, neu: 10+5+10+2+5=32
    assert sentiment_stats["positive"] == 187
    assert sentiment_stats["negative"] == 108
    assert sentiment_stats["neutral"] == 32
    assert sentiment_stats["total"] == 327

    # category_stats: 서비스, 청결, 가격 3개 카테고리
    assert set(category_stats.keys()) == {"서비스", "청결", "가격"}

    # 서비스: pos=120, neg=8, total=140
    assert category_stats["서비스"]["positive"] == 120
    assert category_stats["서비스"]["negative"] == 8
    assert category_stats["서비스"]["total"] == 140

    # 청결: pos=62, neg=50, total=122
    assert category_stats["청결"]["positive"] == 62
    assert category_stats["청결"]["negative"] == 50
    assert category_stats["청결"]["total"] == 122

    # 가격: pos=5, neg=50, total=65
    assert category_stats["가격"]["positive"] == 5
    assert category_stats["가격"]["negative"] == 50
    assert category_stats["가격"]["total"] == 65

    # tag_details: 5개
    assert len(tag_details) == 5


def test_compute_category_stats_empty():
    tag_sentiments, sentiment_stats, category_stats, tag_details = (
        TagStatsCalculator.compute_category_stats([])
    )

    assert tag_sentiments == []
    assert category_stats == {}
    assert tag_details == []
    assert sentiment_stats["positive"] == 0
    assert sentiment_stats["negative"] == 0
    assert sentiment_stats["neutral"] == 0
    assert sentiment_stats["total"] == 0


# ============================================================
# compute_strengths_improvements
# ============================================================


def test_compute_strengths_improvements(sample_branch_tags):
    _, _, category_stats, _ = TagStatsCalculator.compute_category_stats(sample_branch_tags)
    strengths, improvements, strengths_detail, improvements_detail = (
        TagStatsCalculator.compute_strengths_improvements(category_stats)
    )

    # 서비스: pos_ratio = round(120/140*100) = 86% >= 60 → strength
    strength_cats = [s["category_name"] for s in strengths_detail]
    assert "서비스" in strength_cats

    # 가격: neg_ratio = round(50/65*100) = 77% >= 20 → improvement
    improvement_cats = [i["category_name"] for i in improvements_detail]
    assert "가격" in improvement_cats

    # 청결: pos_ratio = round(62/122*100) = 51% < 60 → not a strength
    assert "청결" not in strength_cats

    # strengths 문자열 형식: "카테고리(비율%)"
    assert any("서비스" in s for s in strengths)

    # improvements 문자열 형식: "카테고리(비율%)"
    assert any("가격" in s for s in improvements)


# ============================================================
# compute_top_tags
# ============================================================


def test_compute_top_tags(sample_branch_tags):
    _, _, _, tag_details = TagStatsCalculator.compute_category_stats(sample_branch_tags)
    with patch(
        "services.tag_stats_calculator.AFFILIATE_CATEGORIES",
        _SAMPLE_AFFILIATE_CATEGORIES,
    ):
        top_positive, top_negative, top_tags_detail = (
            TagStatsCalculator.compute_top_tags(tag_details)
        )

    # top_positive는 카테고리별 긍정 수 내림차순: 서비스(120) > 청결(62) > 가격(5)
    assert len(top_positive) >= 1
    assert top_positive[0].tag_name == "서비스"
    assert top_positive[0].count == 120

    # 두 번째는 청결(62)
    assert top_positive[1].tag_name == "청결"
    assert top_positive[1].count == 62

    # top_negative는 카테고리별 부정 수 내림차순: 청결(50) = 가격(50) > 서비스(8)
    assert len(top_negative) >= 1
    assert top_negative[0].count == 50

    # TagRankItem 필드 확인
    item = top_positive[0]
    assert hasattr(item, "tag_name")
    assert hasattr(item, "category_name")
    assert hasattr(item, "count")
    assert hasattr(item, "ratio")

    # top_tags_detail 구조 확인
    assert len(top_tags_detail) >= 1
    assert "name" in top_tags_detail[0]
    assert "count" in top_tags_detail[0]
    assert "positive_ratio" in top_tags_detail[0]


# ============================================================
# compute (async integration)
# ============================================================


@pytest.mark.asyncio
async def test_compute_integration(mock_branch_tag_repo):
    calculator = TagStatsCalculator(mock_branch_tag_repo)
    with patch(
        "services.tag_stats_calculator.AFFILIATE_CATEGORIES",
        _SAMPLE_AFFILIATE_CATEGORIES,
    ):
        result = await calculator.compute(branch_id=1)

    # 레포 호출 확인
    mock_branch_tag_repo.get_by_branch.assert_called_once_with(
        1, period_type="all", limit=100
    )

    # 결과 딕셔너리의 모든 키 존재 확인
    expected_keys = {
        "tag_sentiments",
        "sentiment_stats",
        "strengths",
        "improvements",
        "strengths_detail",
        "improvements_detail",
        "tag_details",
        "top_positive_tags",
        "top_negative_tags",
        "top_tags_detail",
        "tag_by_category",
    }
    assert expected_keys == set(result.keys())

    # 기본 내용 검증
    assert len(result["tag_sentiments"]) == 5
    assert set(result["tag_by_category"].keys()) == {"서비스", "청결", "가격"}
    assert result["sentiment_stats"]["positive"] == 187
    assert result["top_positive_tags"][0].tag_name == "서비스"


@pytest.mark.asyncio
async def test_compute_empty_tags():
    repo = AsyncMock()
    repo.get_by_branch = AsyncMock(return_value=[])
    calculator = TagStatsCalculator(repo)

    result = await calculator.compute(branch_id=99)

    assert result == {}
