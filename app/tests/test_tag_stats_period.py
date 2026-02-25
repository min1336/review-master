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
    """RPC 결과 행 팩토리 (camelCase — 레거시 호환)"""
    base_tags = [
        {"tagId": 1, "tagName": "직원이 친절함", "categoryName": "직원이 친절함", "categoryColor": "#FF0000",
         "positiveCount": 10, "negativeCount": 2, "neutralCount": 1, "totalCount": 13},
        {"tagId": 2, "tagName": "차량이 청결함", "categoryName": "차량이 청결함", "categoryColor": "#00FF00",
         "positiveCount": 8, "negativeCount": 5, "neutralCount": 3, "totalCount": 16},
        {"tagId": 3, "tagName": "가격이 저렴함", "categoryName": "가격이 저렴함", "categoryColor": "#0000FF",
         "positiveCount": 6, "negativeCount": 1, "neutralCount": 2, "totalCount": 9},
        {"tagId": 4, "tagName": "배달이 빠름", "categoryName": "배달 서비스가 우수함", "categoryColor": "#FF0000",
         "positiveCount": 4, "negativeCount": 0, "neutralCount": 1, "totalCount": 5},
        {"tagId": 5, "tagName": "차량외관이 좋음", "categoryName": "차량외관이 좋음", "categoryColor": "#00FF00",
         "positiveCount": 3, "negativeCount": 7, "neutralCount": 0, "totalCount": 10},
    ]
    return base_tags[:count]


def make_rpc_rows_snake(count: int = 5) -> list[dict]:
    """RPC 결과 행 팩토리 (snake_case — 실제 DB 반환 형식)"""
    base_tags = [
        {"tag_id": 1, "tag_name": "직원이 친절함", "category_id": 1, "category_name": "직원이 친절함",
         "positive_count": 10, "negative_count": 2, "neutral_count": 1, "total_count": 13},
        {"tag_id": 2, "tag_name": "차량이 청결함", "category_id": 4, "category_name": "차량이 청결함",
         "positive_count": 8, "negative_count": 5, "neutral_count": 3, "total_count": 16},
        {"tag_id": 3, "tag_name": "가격이 저렴함", "category_id": 3, "category_name": "가격이 저렴함",
         "positive_count": 6, "negative_count": 1, "neutral_count": 2, "total_count": 9},
        {"tag_id": 4, "tag_name": "배달이 빠름", "category_id": 7, "category_name": "배달 서비스가 우수함",
         "positive_count": 4, "negative_count": 0, "neutral_count": 1, "total_count": 5},
        {"tag_id": 5, "tag_name": "차량외관이 좋음", "category_id": 2, "category_name": "차량외관이 좋음",
         "positive_count": 3, "negative_count": 7, "neutral_count": 0, "total_count": 10},
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
        # "직원이 친절함" 카테고리: 태그1(10p,2n)
        assert cat_stats["직원이 친절함"]["positive"] == 10
        assert cat_stats["직원이 친절함"]["negative"] == 2
        # "차량이 청결함" 카테고리: 태그2(8p,5n)
        assert cat_stats["차량이 청결함"]["positive"] == 8
        assert cat_stats["차량이 청결함"]["negative"] == 5

    def test_builds_tag_details(self):
        """tag_details가 올바른 포맷으로 생성되는지"""
        calc, _ = make_calculator()
        rows = make_rpc_rows(2)

        result = calc._compute_from_rpc_rows(rows)

        details = result["tag_details"]
        assert len(details) == 2
        assert details[0]["tag_name"] == "직원이 친절함"
        assert details[0]["category_name"] == "직원이 친절함"

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


# ── Test: snake_case RPC columns (실제 DB 반환 형식) ────

class TestSnakeCaseRpcRows:
    """DB가 snake_case 컬럼명을 반환할 때도 정상 동작하는지 검증"""

    def test_snake_case_converts_tag_sentiments(self):
        """snake_case 행이 올바르게 변환되는지"""
        calc, _ = make_calculator()
        rows = make_rpc_rows_snake(3)

        result = calc._compute_from_rpc_rows(rows)

        assert len(result["tag_sentiments"]) == 3
        first = result["tag_sentiments"][0]
        assert first["name"] == "직원이 친절함"
        assert first["positive"] == 10
        assert first["negative"] == 2

    def test_snake_case_builds_category_stats(self):
        """snake_case 행에서 카테고리 통계가 올바르게 생성되는지"""
        calc, _ = make_calculator()
        rows = make_rpc_rows_snake(5)

        result = calc._compute_from_rpc_rows(rows)

        cat_stats = result["tag_by_category"]
        assert "직원이 친절함" in cat_stats
        assert cat_stats["직원이 친절함"]["positive"] == 10
        assert "차량이 청결함" in cat_stats
        assert cat_stats["차량이 청결함"]["negative"] == 5

    def test_snake_case_tag_details_have_category_name(self):
        """snake_case 행에서 tag_details에 category_name이 포함되는지"""
        calc, _ = make_calculator()
        rows = make_rpc_rows_snake(2)

        result = calc._compute_from_rpc_rows(rows)

        details = result["tag_details"]
        assert details[0]["category_name"] == "직원이 친절함"
        assert details[1]["category_name"] == "차량이 청결함"

    def test_snake_case_top_tags_match_affiliate_categories(self):
        """snake_case 행에서 AFFILIATE_CATEGORIES 필터링이 정상 동작하는지"""
        calc, _ = make_calculator()
        rows = make_rpc_rows_snake(5)

        result = calc._compute_from_rpc_rows(rows)

        # top_positive_tags에 업체 카테고리 태그가 포함되어야 함
        top_pos = result["top_positive_tags"]
        assert len(top_pos) > 0
        assert top_pos[0].tag_name == "직원이 친절함"

    @pytest.mark.asyncio
    async def test_compute_with_snake_case_rpc(self):
        """compute()가 snake_case RPC 결과도 정상 처리하는지"""
        calc, mock_repo = make_calculator()
        mock_repo.get_tag_stats_by_period.return_value = make_rpc_rows_snake(5)

        start = datetime(2025, 1, 1)
        end = datetime(2025, 2, 1)
        result = await calc.compute(1, start, end)

        assert len(result["tag_sentiments"]) == 5
        assert result["top_positive_tags"]  # 비어있지 않아야 함
        mock_repo.get_by_branch.assert_not_awaited()
