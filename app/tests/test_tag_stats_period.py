"""기간별 태그 통계 기능 테스트

TDD: _compute_from_rpc_rows, compute(기간 파라미터), fallback 동작 검증
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.tag_stats_calculator import TagStatsCalculator, MIN_PERIOD_TAG_COUNT


# ── Fixtures ──────────────────────────────────────────────

def make_rpc_rows(count: int = 5) -> list[dict]:
    """RPC 결과 행 팩토리"""
    base_tags = [
        {"tagId": 1, "tagName": "직원이 친절함", "categoryName": "서비스", "categoryColor": "#FF0000",
         "positiveCount": 10, "negativeCount": 2, "neutralCount": 1, "totalCount": 13},
        {"tagId": 2, "tagName": "차량이 청결함", "categoryName": "차량 상태", "categoryColor": "#00FF00",
         "positiveCount": 8, "negativeCount": 5, "neutralCount": 3, "totalCount": 16},
        {"tagId": 3, "tagName": "가격이 저렴함", "categoryName": "가격", "categoryColor": "#0000FF",
         "positiveCount": 6, "negativeCount": 1, "neutralCount": 2, "totalCount": 9},
        {"tagId": 4, "tagName": "배달이 빠름", "categoryName": "서비스", "categoryColor": "#FF0000",
         "positiveCount": 4, "negativeCount": 0, "neutralCount": 1, "totalCount": 5},
        {"tagId": 5, "tagName": "차량외관이 좋음", "categoryName": "차량 상태", "categoryColor": "#00FF00",
         "positiveCount": 3, "negativeCount": 7, "neutralCount": 0, "totalCount": 10},
    ]
    return base_tags[:count]


def make_calculator() -> tuple[TagStatsCalculator, AsyncMock]:
    """TagStatsCalculator + mock repo 팩토리"""
    mock_repo = AsyncMock()
    calc = TagStatsCalculator(mock_repo)
    return calc, mock_repo


# ── Test: _compute_from_rpc_rows ──────────────────────────

class TestComputeFromRpcRows:
    """RPC 결과 행 → 기존 compute() 반환 포맷 변환 테스트"""

    def test_converts_tag_sentiments(self):
        """tag_sentiments 리스트가 올바른 포맷으로 변환되는지"""
        calc, _ = make_calculator()
        rows = make_rpc_rows(3)

        result = calc._compute_from_rpc_rows(rows)

        assert len(result["tag_sentiments"]) == 3
        first = result["tag_sentiments"][0]
        assert first["name"] == "직원이 친절함"
        assert first["positive"] == 10
        assert first["negative"] == 2
        assert first["neutral"] == 1
        assert first["total"] == 13

    def test_aggregates_sentiment_stats(self):
        """전체 감정 통계가 올바르게 집계되는지"""
        calc, _ = make_calculator()
        rows = make_rpc_rows(3)

        result = calc._compute_from_rpc_rows(rows)

        stats = result["sentiment_stats"]
        assert stats["positive"] == 10 + 8 + 6  # 24
        assert stats["negative"] == 2 + 5 + 1   # 8
        assert stats["neutral"] == 1 + 3 + 2    # 6
        assert stats["total"] == 24 + 8 + 6     # 38

    def test_builds_category_stats(self):
        """카테고리별 통계가 올바르게 그룹화되는지"""
        calc, _ = make_calculator()
        rows = make_rpc_rows(5)

        result = calc._compute_from_rpc_rows(rows)

        cat_stats = result["tag_by_category"]
        # "서비스" 카테고리: 태그1(10p,2n) + 태그4(4p,0n)
        assert cat_stats["서비스"]["positive"] == 14
        assert cat_stats["서비스"]["negative"] == 2
        # "차량 상태" 카테고리: 태그2(8p,5n) + 태그5(3p,7n)
        assert cat_stats["차량 상태"]["positive"] == 11
        assert cat_stats["차량 상태"]["negative"] == 12

    def test_builds_tag_details(self):
        """tag_details가 올바른 포맷으로 생성되는지"""
        calc, _ = make_calculator()
        rows = make_rpc_rows(2)

        result = calc._compute_from_rpc_rows(rows)

        details = result["tag_details"]
        assert len(details) == 2
        assert details[0]["tag_name"] == "직원이 친절함"
        assert details[0]["category_name"] == "서비스"

    def test_empty_rows_returns_empty_dict(self):
        """빈 행이면 빈 dict 반환"""
        calc, _ = make_calculator()

        result = calc._compute_from_rpc_rows([])

        assert result == {}

    def test_skips_rows_without_tag_name(self):
        """tagName이 없는 행은 건너뛰기"""
        calc, _ = make_calculator()
        rows = [{"tagId": 1, "tagName": "", "categoryName": "서비스",
                 "positiveCount": 5, "negativeCount": 0, "neutralCount": 0, "totalCount": 5}]

        result = calc._compute_from_rpc_rows(rows)

        assert result == {}

    def test_handles_null_category(self):
        """categoryName이 null이면 category_stats에 추가하지 않음"""
        calc, _ = make_calculator()
        rows = [{"tagId": 1, "tagName": "테스트태그", "categoryName": None,
                 "positiveCount": 5, "negativeCount": 0, "neutralCount": 0, "totalCount": 5}]

        result = calc._compute_from_rpc_rows(rows)

        assert result["tag_by_category"] == {}
        assert len(result["tag_sentiments"]) == 1


# ── Test: compute() with period params ────────────────────

class TestComputeWithPeriod:
    """compute() 기간 파라미터 동작 테스트"""

    @pytest.mark.asyncio
    async def test_uses_rpc_when_period_given_and_sufficient_data(self):
        """기간 파라미터 + 충분한 데이터 → RPC 결과 사용"""
        calc, mock_repo = make_calculator()
        mock_repo.get_tag_stats_by_period.return_value = make_rpc_rows(5)

        start = datetime(2025, 1, 1)
        end = datetime(2025, 2, 1)
        result = await calc.compute(1, start, end)

        mock_repo.get_tag_stats_by_period.assert_awaited_once_with(1, start, end)
        assert len(result["tag_sentiments"]) == 5
        # get_by_branch(all-time fallback)는 호출되지 않아야 함
        mock_repo.get_by_branch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_falls_back_when_period_data_insufficient(self):
        """기간별 데이터 < MIN_PERIOD_TAG_COUNT → fallback"""
        calc, mock_repo = make_calculator()
        mock_repo.get_tag_stats_by_period.return_value = make_rpc_rows(2)  # < 3
        mock_repo.get_by_branch.return_value = []

        start = datetime(2025, 1, 1)
        end = datetime(2025, 2, 1)
        result = await calc.compute(1, start, end)

        # RPC 호출 후 fallback으로 get_by_branch 호출
        mock_repo.get_tag_stats_by_period.assert_awaited_once()
        mock_repo.get_by_branch.assert_awaited_once_with(1, period_type="all", limit=100)

    @pytest.mark.asyncio
    async def test_falls_back_on_rpc_exception(self):
        """RPC 호출 실패 → fallback"""
        calc, mock_repo = make_calculator()
        mock_repo.get_tag_stats_by_period.side_effect = Exception("RPC error")
        mock_repo.get_by_branch.return_value = []

        start = datetime(2025, 1, 1)
        end = datetime(2025, 2, 1)
        result = await calc.compute(1, start, end)

        mock_repo.get_by_branch.assert_awaited_once_with(1, period_type="all", limit=100)

    @pytest.mark.asyncio
    async def test_no_period_tries_rpc_first_then_fallback(self):
        """기간 파라미터 없어도 RPC를 먼저 시도 (기본 범위), 부족하면 fallback"""
        calc, mock_repo = make_calculator()
        mock_repo.get_tag_stats_by_period.return_value = make_rpc_rows(2)  # < MIN
        mock_repo.get_by_branch.return_value = []

        result = await calc.compute(1)

        # RPC는 기본 범위(2020~now)로 항상 호출됨
        mock_repo.get_tag_stats_by_period.assert_awaited_once()
        # 부족하면 fallback
        mock_repo.get_by_branch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_period_rpc_sufficient_skips_fallback(self):
        """기간 파라미터 없어도 RPC 충분하면 fallback 건너뜀"""
        calc, mock_repo = make_calculator()
        mock_repo.get_tag_stats_by_period.return_value = make_rpc_rows(5)

        result = await calc.compute(1)

        mock_repo.get_tag_stats_by_period.assert_awaited_once()
        mock_repo.get_by_branch.assert_not_awaited()
        assert len(result["tag_sentiments"]) == 5

    @pytest.mark.asyncio
    async def test_min_period_tag_count_boundary(self):
        """정확히 MIN_PERIOD_TAG_COUNT개 → RPC 결과 사용"""
        calc, mock_repo = make_calculator()
        mock_repo.get_tag_stats_by_period.return_value = make_rpc_rows(MIN_PERIOD_TAG_COUNT)

        start = datetime(2025, 1, 1)
        end = datetime(2025, 2, 1)
        result = await calc.compute(1, start, end)

        assert len(result["tag_sentiments"]) == MIN_PERIOD_TAG_COUNT
        mock_repo.get_by_branch.assert_not_awaited()
