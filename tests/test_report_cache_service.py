"""ReportCacheService 단위 테스트"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from schemas.report import ReportData, TopTagItem
from services.report_cache_service import ReportCacheService


# ============================================================
# 헬퍼
# ============================================================

def _make_report_data(**kwargs) -> ReportData:
    defaults = dict(
        branch_id=1,
        branch_name="테스트지점",
        affiliate_name="테스트업체",
        period_start="2024-01-01",
        period_end="2024-01-31",
        total_reviews=100,
    )
    defaults.update(kwargs)
    return ReportData(**defaults)


def _make_service(report_repo=None, review_repo=None, branch_tag_repo=None) -> ReportCacheService:
    return ReportCacheService(
        report_repo=report_repo or AsyncMock(),
        review_repo=review_repo or AsyncMock(),
        branch_tag_repo=branch_tag_repo or AsyncMock(),
    )


START = datetime(2024, 1, 1)
END = datetime(2024, 1, 31)


# ============================================================
# get_saved_report
# ============================================================

@pytest.mark.asyncio
async def test_get_saved_report_found(mock_report_repo):
    """repo가 report_data dict를 포함한 레코드를 반환하면 ReportData 인스턴스를 돌려준다."""
    report_dict = dict(
        branch_id=1,
        branch_name="테스트지점",
        affiliate_name="테스트업체",
        period_start="2024-01-01",
        period_end="2024-01-31",
        total_reviews=50,
    )
    mock_report_repo.get_by_branch_and_period = AsyncMock(
        return_value={"report_data": report_dict}
    )

    service = _make_service(report_repo=mock_report_repo)
    result = await service.get_saved_report(1, START, END)

    assert isinstance(result, ReportData)
    assert result.branch_id == 1
    assert result.branch_name == "테스트지점"
    assert result.total_reviews == 50
    mock_report_repo.get_by_branch_and_period.assert_awaited_once_with(1, START, END)


@pytest.mark.asyncio
async def test_get_saved_report_not_found(mock_report_repo):
    """repo가 None을 반환하면 None을 돌려준다."""
    mock_report_repo.get_by_branch_and_period = AsyncMock(return_value=None)

    service = _make_service(report_repo=mock_report_repo)
    result = await service.get_saved_report(1, START, END)

    assert result is None


@pytest.mark.asyncio
async def test_get_saved_report_no_repo():
    """report_repo가 None이면 None을 돌려준다."""
    service = ReportCacheService(
        report_repo=None,
        review_repo=AsyncMock(),
        branch_tag_repo=AsyncMock(),
    )
    result = await service.get_saved_report(1, START, END)
    assert result is None


# ============================================================
# get_report_list
# ============================================================

@pytest.mark.asyncio
async def test_get_report_list(mock_report_repo):
    """get_report_list는 repo.get_all_by_branch에 위임하고 결과를 그대로 반환한다."""
    expected = [{"id": 1, "created_at": "2024-01-31"}]
    mock_report_repo.get_all_by_branch = AsyncMock(return_value=expected)

    service = _make_service(report_repo=mock_report_repo)
    result = await service.get_report_list(branch_id=42, limit=5)

    assert result == expected
    mock_report_repo.get_all_by_branch.assert_awaited_once_with(42, 5)


# ============================================================
# extract_saved_tag_stats
# ============================================================

def test_extract_saved_tag_stats():
    """top_tags_detail이 있으면 (총 언급 수, 가중 평균 긍정률)을 반환한다."""
    tag1 = TopTagItem(name="친절", count=50, positive_ratio=80)
    tag2 = TopTagItem(name="청결", count=30, positive_ratio=60)
    report = _make_report_data(top_tags_detail=[tag1, tag2])

    result = ReportCacheService.extract_saved_tag_stats(report)

    assert result is not None
    total, pos_ratio = result

    assert total == 80  # 50 + 30
    expected_pos_ratio = (80 * 50 + 60 * 30) / 80  # 72.5
    assert abs(pos_ratio - expected_pos_ratio) < 1e-9


def test_extract_saved_tag_stats_empty():
    """top_tags_detail이 비어 있으면 None을 반환한다."""
    report = _make_report_data(top_tags_detail=[])
    result = ReportCacheService.extract_saved_tag_stats(report)
    assert result is None


# ============================================================
# should_invalidate_cache
# ============================================================

@pytest.mark.asyncio
async def test_should_invalidate_below_min_reviews(mock_review_repo):
    """새 리뷰 수가 CACHE_MIN_NEW_REVIEWS 미만이면 무효화하지 않는다."""
    # saved total=100, current count=104 → new_reviews=4 < 5
    mock_review_repo.count_by_branch = AsyncMock(return_value=104)
    saved_report = _make_report_data(total_reviews=100)

    service = _make_service(review_repo=mock_review_repo)
    result = await service.should_invalidate_cache(1, START, END, saved_report)

    assert result is False


@pytest.mark.asyncio
async def test_should_invalidate_significant_drift(mock_review_repo, mock_branch_tag_repo):
    """긍정률 변화가 CACHE_SENTIMENT_DRIFT(8%p) 이상이면 True를 반환한다."""
    # saved: count=50, positive_ratio=80 → saved_pos_ratio=80.0
    tag = TopTagItem(name="친절", count=50, positive_ratio=80)
    saved_report = _make_report_data(total_reviews=100, top_tags_detail=[tag])

    # current: new_reviews=100-100+20=20 → current count=120
    mock_review_repo.count_by_branch = AsyncMock(return_value=120)

    # branch_tag_repo가 돌려주는 태그: positive=30, negative=70 → pos_ratio=30%
    # drift = |30.0 - 80.0| = 50%p >= 8%p → signal_b=True
    fake_tag = MagicMock()
    fake_tag.positive_count = 30
    fake_tag.negative_count = 70
    mock_branch_tag_repo.get_by_branch = AsyncMock(return_value=[fake_tag])

    service = _make_service(
        review_repo=mock_review_repo,
        branch_tag_repo=mock_branch_tag_repo,
    )
    result = await service.should_invalidate_cache(1, START, END, saved_report)

    assert result is True


# ============================================================
# Gap A: Signal A (tag count ratio)
# ============================================================

class _FakeTag:
    def __init__(self, pos, neg):
        self.positive_count = pos
        self.negative_count = neg


@pytest.mark.asyncio
async def test_should_invalidate_signal_a_tag_count():
    """Signal A: 태그 수 변화 >= 15%일 때 캐시 무효화 (감정 drift 없이)"""
    # saved: total_reviews=100, top_tags_detail 총 count=100, positive_ratio=70
    tag = TopTagItem(name="친절", count=100, positive_ratio=70)
    saved_report = _make_report_data(total_reviews=100, top_tags_detail=[tag])

    # new_reviews = 120 - 100 = 20 >= CACHE_MIN_NEW_REVIEWS(5)
    review_repo = AsyncMock()
    review_repo.count_by_branch = AsyncMock(return_value=120)

    # current_total = 84 + 36 = 120 (20% increase >= CACHE_TAG_COUNT_RATIO 15%)
    # current_pos_ratio = 84/120 * 100 = 70.0 → drift = |70.0 - 70.0| = 0 → Signal B False
    branch_tag_repo = AsyncMock()
    branch_tag_repo.get_by_branch = AsyncMock(
        return_value=[_FakeTag(pos=84, neg=36)]
    )

    service = _make_service(review_repo=review_repo, branch_tag_repo=branch_tag_repo)
    result = await service.should_invalidate_cache(1, START, END, saved_report)

    assert result is True


# ============================================================
# Gap B: JSON string deserialization
# ============================================================

@pytest.mark.asyncio
async def test_get_saved_report_json_string():
    """report_data가 JSON 문자열로 저장된 경우 파싱"""
    report_dict = {
        "branch_id": 1,
        "branch_name": "test",
        "affiliate_name": "test",
        "period_start": "2024-01-01",
        "period_end": "2024-03-31",
        "total_reviews": 50,
    }
    report_repo = AsyncMock()
    report_repo.get_by_branch_and_period = AsyncMock(
        return_value={"report_data": json.dumps(report_dict)}
    )

    service = _make_service(report_repo=report_repo)
    result = await service.get_saved_report(1, START, END)

    assert isinstance(result, ReportData)
    assert result.branch_id == 1


# ============================================================
# Gap C: Fallback when top_tags_detail is empty
# ============================================================

@pytest.mark.asyncio
async def test_should_invalidate_fallback_no_tag_stats():
    """top_tags_detail이 비어 있으면 리뷰 수 변화만으로 판단"""
    # saved: total_reviews=100, top_tags_detail=[]
    saved_report = _make_report_data(total_reviews=100, top_tags_detail=[])

    # new_reviews = 135 - 100 = 35 >= REVIEW_CHANGE_THRESHOLD(30)
    review_repo = AsyncMock()
    review_repo.count_by_branch = AsyncMock(return_value=135)

    service = _make_service(review_repo=review_repo)
    result = await service.should_invalidate_cache(1, START, END, saved_report)

    assert result is True


@pytest.mark.asyncio
async def test_should_invalidate_fallback_below_threshold():
    """top_tags_detail이 비어 있고 리뷰 변화가 임계값 미만이면 False"""
    # saved: total_reviews=100, top_tags_detail=[]
    saved_report = _make_report_data(total_reviews=100, top_tags_detail=[])

    # new_reviews = 125 - 100 = 25 < REVIEW_CHANGE_THRESHOLD(30)
    review_repo = AsyncMock()
    review_repo.count_by_branch = AsyncMock(return_value=125)

    service = _make_service(review_repo=review_repo)
    result = await service.should_invalidate_cache(1, START, END, saved_report)

    assert result is False
