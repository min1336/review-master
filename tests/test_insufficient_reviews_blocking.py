"""리뷰 30개 이하 시 요약/리포트 생성 차단 테스트

전체기간 리뷰 개수가 MIN_REVIEWS_FOR_SUMMARY(30) 이하이면
요약과 리포트를 생성하지 않고 실패/빈 결과를 반환하는지 검증합니다.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============================================================
# Helper: ORM session mock for summary_service
# ============================================================


def _make_mock_session(counts: list[int]):
    """ORM session mock — execute 호출마다 counts 값을 순서대로 반환

    Args:
        counts: scalar_one()이 반환할 값 리스트 (기간별 쿼리 순서대로)

    Returns:
        (factory, session) — factory는 patch 대상, session은 검증용
    """
    results = []
    for c in counts:
        r = MagicMock()
        r.scalar_one.return_value = c
        results.append(r)

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=results)
    session.close = AsyncMock()

    factory = MagicMock(return_value=session)
    return factory


# ============================================================
# SummaryService — generate_summary_with_data 차단 테스트
# ============================================================


class TestSummaryServiceInsufficientReviews:
    """전체 리뷰가 30개 이하일 때 요약 생성이 차단되는지 검증"""

    def _make_service(self, summary_repo=None, branch_tag_repo=None, review_repo=None):
        from services.summary_service import SummaryService

        return SummaryService(
            summary_repo=summary_repo or AsyncMock(),
            branch_tag_repo=branch_tag_repo or AsyncMock(),
            review_repo=review_repo or AsyncMock(),
        )

    def _mock_summary_repo(self):
        """get_by_branch_id가 유효한 지점 정보를 반환하는 mock"""
        repo = AsyncMock()
        summary = MagicMock()
        summary.model_dump.return_value = {
            "branch_name": "테스트지점",
            "affiliate_name": "테스트업체",
            "review_count": 0,
            "region": "서울",
        }
        repo.get_by_branch_id = AsyncMock(return_value=summary)
        return repo

    @pytest.mark.asyncio
    async def test_blocks_when_total_count_is_zero(self):
        """전체 리뷰 0건 → 기존 동작 유지 (실패 반환)"""
        summary_repo = self._mock_summary_repo()
        service = self._make_service(summary_repo=summary_repo)

        # 4개 기간 쿼리 → 0, 전체 쿼리 → 0
        factory = _make_mock_session([0, 0, 0, 0, 0])

        with patch("repository.database.get_session_factory", return_value=factory):
            result = await service.generate_summary_with_data(branch_id=1)

        assert result["success"] is False
        assert result["review_count"] == 0
        assert "부족" in result["error"]

    @pytest.mark.asyncio
    async def test_blocks_when_total_count_is_15(self):
        """전체 리뷰 15건 → 생성 차단 (신규 동작)"""
        summary_repo = self._mock_summary_repo()
        service = self._make_service(summary_repo=summary_repo)

        # 4개 기간 쿼리 → 0, 전체 쿼리 → 15
        factory = _make_mock_session([0, 0, 0, 0, 15])

        with patch("repository.database.get_session_factory", return_value=factory):
            result = await service.generate_summary_with_data(branch_id=1)

        assert result["success"] is False
        assert result["review_count"] == 15
        assert "부족" in result["error"]

    @pytest.mark.asyncio
    async def test_blocks_when_total_count_is_exactly_30(self):
        """전체 리뷰 정확히 30건 → 생성 차단 (<= 조건)"""
        summary_repo = self._mock_summary_repo()
        service = self._make_service(summary_repo=summary_repo)

        # 4개 기간 쿼리 → 0, 전체 쿼리 → 30
        factory = _make_mock_session([0, 0, 0, 0, 30])

        with patch("repository.database.get_session_factory", return_value=factory):
            result = await service.generate_summary_with_data(branch_id=1)

        assert result["success"] is False
        assert result["review_count"] == 30
        assert "부족" in result["error"]

    @pytest.mark.asyncio
    async def test_insufficient_message_includes_actual_count(self):
        """실패 메시지에 실제 리뷰 수가 포함되는지 확인"""
        summary_repo = self._mock_summary_repo()
        service = self._make_service(summary_repo=summary_repo)

        factory = _make_mock_session([0, 0, 0, 0, 15])

        with patch("repository.database.get_session_factory", return_value=factory):
            result = await service.generate_summary_with_data(branch_id=1)

        assert "15건" in result["summary"]

    @pytest.mark.asyncio
    async def test_allows_when_total_count_is_31(self):
        """전체 리뷰 31건 → 'all' 기간으로 정상 진행 (차단되지 않음)"""
        summary_repo = self._mock_summary_repo()
        branch_tag_repo = AsyncMock()
        branch_tag_repo.get_by_branch = AsyncMock(return_value=[])
        service = self._make_service(
            summary_repo=summary_repo,
            branch_tag_repo=branch_tag_repo,
        )

        # 4개 기간 쿼리 → 0, 전체 쿼리 → 31, 추가 쿼리용 여유분
        factory = _make_mock_session([0, 0, 0, 0, 31, 0, 0, 0, 0, 0])

        mock_response = MagicMock()
        mock_response.content = "테스트 요약"

        mock_provider = AsyncMock()
        mock_provider.async_generate = AsyncMock(return_value=mock_response)

        with (
            patch("repository.database.get_session_factory", return_value=factory),
            patch("infrastructure.llm.get_provider", return_value=mock_provider),
            patch("infrastructure.llm.prompts.SummaryPromptBuilder") as mock_builder_cls,
            patch("infrastructure.llm.prompts.OperationalSummaryPromptBuilder"),
        ):
            mock_builder_cls.create_enhanced_summary_prompt.return_value = ("system", "user")
            mock_builder_cls.get_insufficient_reviews_message.return_value = ""

            result = await service.generate_summary_with_data(branch_id=1)

        # 차단되지 않았음을 확인 (success True 또는 period가 "all")
        assert result.get("success") is not False or result.get("period") == "all"

    @pytest.mark.asyncio
    async def test_period_selection_bypasses_blocking(self):
        """1m에 50건 → 1m 기간 선택, 차단 로직 미진입"""
        summary_repo = self._mock_summary_repo()
        branch_tag_repo = AsyncMock()
        branch_tag_repo.get_by_branch = AsyncMock(return_value=[])
        service = self._make_service(
            summary_repo=summary_repo,
            branch_tag_repo=branch_tag_repo,
        )

        # 첫 번째 기간(1m) 쿼리 → 50 (>= 30, break), 추가 쿼리 여유분
        factory = _make_mock_session([50, 0, 0, 0, 0, 0, 0, 0])

        mock_response = MagicMock()
        mock_response.content = "테스트 요약"

        mock_provider = AsyncMock()
        mock_provider.async_generate = AsyncMock(return_value=mock_response)

        with (
            patch("repository.database.get_session_factory", return_value=factory),
            patch("infrastructure.llm.get_provider", return_value=mock_provider),
            patch("infrastructure.llm.prompts.SummaryPromptBuilder") as mock_builder_cls,
            patch("infrastructure.llm.prompts.OperationalSummaryPromptBuilder"),
        ):
            mock_builder_cls.create_enhanced_summary_prompt.return_value = ("system", "user")

            result = await service.generate_summary_with_data(branch_id=1)

        # 차단 로직에 진입하지 않으므로 success가 False가 아님
        assert result.get("success") is not False or result.get("period") is not None


# ============================================================
# ReportService — generate_report_with_progress 차단 테스트
# ============================================================


class TestReportServiceInsufficientReviews:
    """리포트 생성 시 리뷰 30개 이하 차단 검증"""

    def _make_service(self, **kwargs):
        from services.report_service import ReportService

        return ReportService(
            summary_repo=kwargs.get("summary_repo", AsyncMock()),
            review_repo=kwargs.get("review_repo", AsyncMock()),
            branch_tag_repo=kwargs.get("branch_tag_repo", AsyncMock()),
            report_repo=kwargs.get("report_repo", None),
            sentiment_repo=kwargs.get("sentiment_repo", None),
            vehicle_analyzer=kwargs.get("vehicle_analyzer", MagicMock()),
            cache_service=kwargs.get("cache_service", None),
            tag_calculator=kwargs.get("tag_calculator", None),
            ai_generator=kwargs.get("ai_generator", None),
        )

    @pytest.mark.asyncio
    async def test_blocks_when_total_reviews_is_zero(self):
        """collected total_reviews=0 → 빈 리포트 반환 (기존 동작 유지)"""
        from schemas.report import ReportData

        service = self._make_service()
        service._step_collect = AsyncMock(return_value={
            "branch_name": "테스트지점",
            "affiliate_name": "테스트업체",
            "total_reviews": 0,
        })

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        result = await service.generate_report_with_progress(
            branch_id=1, start_date=start, end_date=end
        )

        assert isinstance(result, ReportData)
        assert result.total_reviews == 0
        assert result.period_summary == ""  # 빈 리포트

    @pytest.mark.asyncio
    async def test_blocks_when_total_reviews_is_20(self):
        """collected total_reviews=20 → 빈 리포트 반환 (신규 동작)"""
        from schemas.report import ReportData

        service = self._make_service()
        service._step_collect = AsyncMock(return_value={
            "branch_name": "테스트지점",
            "affiliate_name": "테스트업체",
            "total_reviews": 20,
        })

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        result = await service.generate_report_with_progress(
            branch_id=1, start_date=start, end_date=end
        )

        assert isinstance(result, ReportData)
        assert result.total_reviews == 20
        assert result.period_summary == ""

    @pytest.mark.asyncio
    async def test_blocks_when_total_reviews_is_exactly_30(self):
        """collected total_reviews=30 → 빈 리포트 반환 (<= 조건)"""
        from schemas.report import ReportData

        service = self._make_service()
        service._step_collect = AsyncMock(return_value={
            "branch_name": "테스트지점",
            "affiliate_name": "테스트업체",
            "total_reviews": 30,
        })

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        result = await service.generate_report_with_progress(
            branch_id=1, start_date=start, end_date=end
        )

        assert isinstance(result, ReportData)
        assert result.total_reviews == 30
        assert result.period_summary == ""

    @pytest.mark.asyncio
    async def test_returns_actual_review_count_in_blocked_report(self):
        """차단된 리포트에도 실제 리뷰 수가 반영되는지 확인"""
        from schemas.report import ReportData

        service = self._make_service()
        service._step_collect = AsyncMock(return_value={
            "branch_name": "테스트지점",
            "affiliate_name": "테스트업체",
            "total_reviews": 15,
        })

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        result = await service.generate_report_with_progress(
            branch_id=1, start_date=start, end_date=end
        )

        assert result.total_reviews == 15  # 0이 아닌 실제 값


# ============================================================
# ReportService — get_review_count_summary 추천 기간 테스트
# ============================================================


class TestReviewCountSummaryRecommendation:
    """추천 기간 로직에서 리뷰 부족 시 recommended_period=None 반환 검증"""

    def _make_service(self, review_repo=None, **kwargs):
        from services.report_service import ReportService

        return ReportService(
            summary_repo=kwargs.get("summary_repo", AsyncMock()),
            review_repo=review_repo or AsyncMock(),
            branch_tag_repo=kwargs.get("branch_tag_repo", AsyncMock()),
            report_repo=kwargs.get("report_repo", None),
            sentiment_repo=kwargs.get("sentiment_repo", None),
            vehicle_analyzer=kwargs.get("vehicle_analyzer", MagicMock()),
        )

    @pytest.mark.asyncio
    async def test_recommended_none_when_all_counts_below_threshold(self):
        """모든 기간 + 전체 리뷰 <= 30 → recommended_period=None, sufficient=False"""
        review_repo = AsyncMock()
        # count_by_branch: 선택기간=10, 1m=5, 3m=10, 6m=15, 12m=20, all=25
        review_repo.count_by_branch = AsyncMock(
            side_effect=[10, 5, 10, 15, 20, 25]
        )

        service = self._make_service(review_repo=review_repo)

        result = await service.get_review_count_summary(
            branch_id=1,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 3, 31),
        )

        assert result["recommended_period"] is None
        assert result["sufficient"] is False

    @pytest.mark.asyncio
    async def test_recommended_all_when_only_all_exceeds_threshold(self):
        """표준 기간 모두 < 30, all > 30 → recommended_period='all', sufficient=True"""
        review_repo = AsyncMock()
        # count_by_branch: 선택기간=10, 1m=5, 3m=10, 6m=15, 12m=20, all=50
        review_repo.count_by_branch = AsyncMock(
            side_effect=[10, 5, 10, 15, 20, 50]
        )

        service = self._make_service(review_repo=review_repo)

        result = await service.get_review_count_summary(
            branch_id=1,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 3, 31),
        )

        assert result["recommended_period"] == "all"
        assert result["sufficient"] is True

    @pytest.mark.asyncio
    async def test_recommended_all_blocked_when_exactly_30(self):
        """all=30 (경계값) → recommended_period=None (> 조건이므로 차단)"""
        review_repo = AsyncMock()
        # count_by_branch: 선택기간=10, 1m=5, 3m=10, 6m=15, 12m=20, all=30
        review_repo.count_by_branch = AsyncMock(
            side_effect=[10, 5, 10, 15, 20, 30]
        )

        service = self._make_service(review_repo=review_repo)

        result = await service.get_review_count_summary(
            branch_id=1,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 3, 31),
        )

        assert result["recommended_period"] is None
        assert result["sufficient"] is False

    @pytest.mark.asyncio
    async def test_sufficient_field_exists_in_response(self):
        """응답에 sufficient 필드가 항상 포함되는지 확인"""
        review_repo = AsyncMock()
        review_repo.count_by_branch = AsyncMock(
            side_effect=[100, 50, 80, 100, 120, 200]
        )

        service = self._make_service(review_repo=review_repo)

        result = await service.get_review_count_summary(
            branch_id=1,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 3, 31),
        )

        assert "sufficient" in result
        assert result["sufficient"] is True
        assert result["recommended_period"] == "1m"
