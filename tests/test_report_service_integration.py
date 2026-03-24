"""ReportService 및 ReportAIGenerator 통합 테스트

리팩토링된 모듈들의 위임 관계와 동작을 검증합니다.
"""

from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


# ============================================================
# ReportService Delegation Tests
# ============================================================


class TestReportServiceDelegation:
    """ReportService가 각 하위 서비스에 올바르게 위임하는지 검증"""

    def _make_service(self, **kwargs):
        """ReportService 인스턴스 생성 헬퍼 (vehicle_analyzer 자동 주입 방지)"""
        from services.report_service import ReportService

        vehicle_analyzer = kwargs.pop("vehicle_analyzer", MagicMock())
        return ReportService(
            summary_repo=kwargs.get("summary_repo", AsyncMock()),
            review_repo=kwargs.get("review_repo", AsyncMock()),
            branch_tag_repo=kwargs.get("branch_tag_repo", AsyncMock()),
            report_repo=kwargs.get("report_repo", None),
            sentiment_repo=kwargs.get("sentiment_repo", None),
            vehicle_analyzer=vehicle_analyzer,
            cache_service=kwargs.get("cache_service", None),
            tag_calculator=kwargs.get("tag_calculator", None),
            ai_generator=kwargs.get("ai_generator", None),
        )

    @pytest.mark.asyncio
    async def test_get_saved_report_delegates_to_cache_service(self):
        """get_saved_report는 cache_service.get_saved_report에 위임한다"""
        expected_report = MagicMock()
        cache_service = AsyncMock()
        cache_service.get_saved_report = AsyncMock(return_value=expected_report)

        service = self._make_service(cache_service=cache_service)

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        result = await service.get_saved_report(branch_id=1, start_date=start, end_date=end)

        cache_service.get_saved_report.assert_awaited_once_with(1, start, end)
        assert result is expected_report

    @pytest.mark.asyncio
    async def test_get_report_list_delegates_to_cache_service(self):
        """get_report_list는 cache_service.get_report_list에 위임한다"""
        expected_list = [{"id": 1}, {"id": 2}]
        cache_service = AsyncMock()
        cache_service.get_report_list = AsyncMock(return_value=expected_list)

        service = self._make_service(cache_service=cache_service)

        result = await service.get_report_list(branch_id=5, limit=10)

        cache_service.get_report_list.assert_awaited_once_with(5, 10)
        assert result == expected_list

    @pytest.mark.asyncio
    async def test_step_tags_delegates_to_tag_calculator(self):
        """_step_tags는 tag_calculator.compute에 위임한다"""
        expected_tags = {"strengths": ["서비스"], "improvements": ["청결"]}
        tag_calculator = AsyncMock()
        tag_calculator.compute = AsyncMock(return_value=expected_tags)

        service = self._make_service(tag_calculator=tag_calculator)

        result = await service._step_tags(branch_id=42)

        tag_calculator.compute.assert_awaited_once_with(42, None, None)
        assert result == expected_tags

    @pytest.mark.asyncio
    async def test_step_ai_delegates_to_ai_generator(self):
        """_step_ai는 ai_generator.generate_all에 위임한다"""
        expected_ai = {
            "period_summary": "요약 텍스트",
            "affiliate_ai_text": "업체 평가",
            "vehicle_ai_text": "차량 평가",
        }
        ai_generator = AsyncMock()
        ai_generator.generate_all = AsyncMock(return_value=expected_ai)

        service = self._make_service(ai_generator=ai_generator)

        data = {"branch_name": "테스트지점", "tags": []}
        result = await service._step_ai(data)

        ai_generator.generate_all.assert_awaited_once_with(data, report_config=None)
        assert result == expected_ai

    @pytest.mark.asyncio
    async def test_get_or_generate_report_returns_cached(self):
        """저장된 리포트가 있고 캐시 무효화가 불필요하면 (saved, False) 반환"""
        from schemas.report import ReportData

        saved_report = ReportData(
            branch_id=1,
            branch_name="테스트지점",
            affiliate_name="테스트업체",
            period_start="2024-01-01",
            period_end="2024-01-31",
            total_reviews=100,
        )

        cache_service = AsyncMock()
        cache_service.get_saved_report = AsyncMock(return_value=saved_report)
        cache_service.should_invalidate_cache = AsyncMock(return_value=False)

        service = self._make_service(cache_service=cache_service)

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        report, is_new = await service.get_or_generate_report(
            branch_id=1, start_date=start, end_date=end
        )

        assert report is saved_report
        assert is_new is False
        cache_service.should_invalidate_cache.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_or_generate_report_generates_new(self):
        """저장된 리포트가 없으면 generate_report를 호출하여 신규 생성한다"""
        from schemas.report import ReportData

        new_report = ReportData(
            branch_id=1,
            branch_name="테스트지점",
            affiliate_name="테스트업체",
            period_start="2024-01-01",
            period_end="2024-01-31",
            total_reviews=50,
        )

        cache_service = AsyncMock()
        cache_service.get_saved_report = AsyncMock(return_value=None)

        service = self._make_service(cache_service=cache_service)

        # generate_report를 직접 패치하여 실제 LLM 호출 방지
        service.generate_report = AsyncMock(return_value=new_report)

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        report, is_new = await service.get_or_generate_report(
            branch_id=1, start_date=start, end_date=end
        )

        service.generate_report.assert_awaited_once_with(1, start, end)
        assert report is new_report
        assert is_new is True

    @pytest.mark.asyncio
    async def test_step_build_assembly(self):
        """_step_build가 upstream 결과를 올바르게 ReportData로 조립하는지 검증"""
        from schemas.report import ReportData

        mock_report_repo = AsyncMock()
        mock_report_repo.save = AsyncMock(return_value=None)

        mock_vehicle_analyzer = MagicMock()
        mock_vehicle_analyzer.build_vehicle_rankings = MagicMock(return_value=([], []))

        service = self._make_service(
            report_repo=mock_report_repo,
            vehicle_analyzer=mock_vehicle_analyzer,
        )

        collected = {
            "branch_id": 1,
            "branch_name": "테스트지점",
            "affiliate_name": "테스트업체",
            "total_reviews": 100,
            "tags": ["친절"],
            "vehicle_analysis": [],
            "vehicle_tags_raw": {},
        }
        tags = {
            "strengths": ["서비스(80%)"],
            "improvements": ["가격(40%)"],
            "strengths_detail": [{"category_name": "서비스", "ratio": 80}],
            "improvements_detail": [{"category_name": "가격", "ratio": 40}],
            "top_tags_detail": [{"name": "친절", "count": 50, "positive_ratio": 85}],
            "top_positive_tags": [],
            "top_negative_tags": [],
        }
        ai = {
            "period_summary": "테스트 요약입니다.",
            "affiliate_ai_text": "업체 평가 텍스트",
            "vehicle_ai_text": "차량 평가 텍스트",
        }
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 3, 31)

        report = await service._step_build(collected, tags, ai, start_date, end_date)

        assert isinstance(report, ReportData)
        assert report.period_summary == "테스트 요약입니다."
        assert report.strengths == ["서비스(80%)"]
        assert report.improvements == ["가격(40%)"]
        assert len(report.strengths_detail) == 1
        assert report.strengths_detail[0].category_name == "서비스"
        assert len(report.top_tags_detail) == 1
        assert report.affiliate_evaluation.ai_text == ""
        assert report.vehicle_evaluation.ai_text == ""
        mock_report_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_or_generate_report_invalidates_cache(self):
        """캐시 무효화 시 리포트를 재생성하는지 검증"""
        from schemas.report import ReportData

        saved_report = ReportData(
            branch_id=1,
            branch_name="테스트지점",
            affiliate_name="테스트업체",
            period_start="2024-01-01",
            period_end="2024-03-31",
            total_reviews=100,
        )
        new_report = ReportData(
            branch_id=1,
            branch_name="테스트지점",
            affiliate_name="테스트업체",
            period_start="2024-01-01",
            period_end="2024-03-31",
            total_reviews=150,
        )

        cache_service = AsyncMock()
        cache_service.get_saved_report = AsyncMock(return_value=saved_report)
        cache_service.should_invalidate_cache = AsyncMock(return_value=True)

        service = self._make_service(cache_service=cache_service)
        service.generate_report = AsyncMock(return_value=new_report)

        start = datetime(2024, 1, 1)
        end = datetime(2024, 3, 31)
        report, is_new = await service.get_or_generate_report(
            branch_id=1, start_date=start, end_date=end
        )

        assert is_new is True
        service.generate_report.assert_awaited_once_with(1, start, end)
        assert report is new_report


# ============================================================
# ReportAIGenerator Tests
# ============================================================


class TestReportAIGenerator:
    """ReportAIGenerator 단위 테스트"""

    def _make_generator(self, summary_repo=None, review_repo=None):
        from services.report_ai_generator import ReportAIGenerator

        return ReportAIGenerator(
            summary_repo=summary_repo or AsyncMock(),
            review_repo=review_repo or AsyncMock(),
        )

    def test_build_vehicle_summary(self):
        """차량 분석 목록에서 요약 텍스트를 올바르게 생성한다"""
        from services.report_ai_generator import ReportAIGenerator

        vehicle_analysis = [
            {
                "model": "소나타",
                "count": 20,
                "like_ratio": 80,
                "dislike_ratio": 20,
                "top_praise": "연비 좋음",
                "top_issue": "실내 소음",
            },
            {
                "model": "아반떼",
                "count": 10,
                "like_ratio": 70,
                "dislike_ratio": 30,
                "top_praise": "경제적",
                "top_issue": "",
            },
        ]

        result = ReportAIGenerator._build_vehicle_summary(vehicle_analysis)

        assert result is not None
        assert "소나타" in result
        assert "20건" in result
        assert "연비 좋음" in result
        assert "실내 소음" in result
        assert "아반떼" in result

    def test_build_vehicle_summary_empty(self):
        """빈 차량 분석 목록은 None을 반환한다"""
        from services.report_ai_generator import ReportAIGenerator

        result = ReportAIGenerator._build_vehicle_summary([])

        assert result is None

    @pytest.mark.asyncio
    async def test_generate_all_structure(self):
        """generate_all은 period_summary, affiliate_ai_text, vehicle_ai_text 키를 포함한 dict를 반환한다"""
        review_repo = AsyncMock()
        review_repo.get_by_branch = AsyncMock(
            return_value=MagicMock(reviews=[{"content": "좋아요"}])
        )

        summary_repo = AsyncMock()
        summary_mock = MagicMock()
        summary_mock.model_dump.return_value = {}
        summary_repo.get_by_branch_id = AsyncMock(return_value=None)

        generator = self._make_generator(
            summary_repo=summary_repo, review_repo=review_repo
        )

        data = {
            "branch_id": 1,
            "branch_name": "테스트지점",
            "total_reviews": 30,
            "tags": ["친절", "청결"],
            "start_date": datetime(2024, 1, 1),
            "end_date": datetime(2024, 1, 31),
            "tag_sentiments": [
                {"name": "친절", "positive": 20, "negative": 2, "neutral": 3, "total": 25}
            ],
            "sentiment_stats": {"positive": 25, "negative": 3, "neutral": 2, "total": 30},
            "tag_details": [],
            "top_positive_tags": [],
            "top_negative_tags": [],
            "top_liked_vehicles": [],
            "top_disliked_vehicles": [],
            "vehicle_analysis": [],
        }

        mock_response = MagicMock()
        mock_response.content = "테스트 요약 텍스트입니다."

        mock_provider = AsyncMock()
        mock_provider.async_generate = AsyncMock(return_value=mock_response)

        mock_builder = MagicMock()
        mock_builder.create_report_prompt = MagicMock(
            return_value=("system", "user")
        )
        mock_builder.create_prompt = MagicMock(
            return_value=("system", "user")
        )
        mock_builder.create_affiliate_evaluation_prompt = MagicMock(
            return_value=("system", "user")
        )
        mock_builder.create_vehicle_evaluation_prompt = MagicMock(
            return_value=("system", "user")
        )

        with (
            patch("infrastructure.llm.get_provider", return_value=mock_provider),
            patch(
                "infrastructure.llm.prompts.RichSummaryPromptBuilder",
                mock_builder,
            ),
            patch(
                "infrastructure.llm.prompts.RichSummaryPromptBuilder",
                mock_builder,
            ),
        ):
            # _generate_period_summary와 _generate_evaluation_text 내부의 import를 패치
            with (
                patch(
                    "services.report_ai_generator.ReportAIGenerator._generate_period_summary",
                    new_callable=AsyncMock,
                    return_value="기간 요약 텍스트",
                ),
                patch(
                    "services.report_ai_generator.ReportAIGenerator._generate_evaluation_text",
                    new_callable=AsyncMock,
                    return_value="평가 텍스트",
                ),
            ):
                result = await generator.generate_all(data)

        assert isinstance(result, dict)
        assert "period_summary" in result
        assert "affiliate_ai_text" in result
        assert "vehicle_ai_text" in result

    @pytest.mark.asyncio
    async def test_generate_evaluation_text_empty_filter(self):
        """카테고리 필터에 매칭 태그가 없으면 빈 문자열 반환"""
        generator = self._make_generator()

        result = await generator._generate_evaluation_text(
            branch_name="test",
            tag_details=[
                {
                    "tag_name": "x",
                    "category_name": "없는카테고리",
                    "positive": 1,
                    "negative": 0,
                    "total": 1,
                }
            ],
            category_filter={"서비스"},
            prompt_method="create_affiliate_evaluation_prompt",
            top_positive=[],
            top_negative=[],
            sample_reviews=None,
            label="업체",
        )

        assert result == ""


# ============================================================
# ReportData Model Tests
# ============================================================


class TestReportDataModel:
    """ReportData Pydantic 모델 동작 검증"""

    def test_report_data_creation(self):
        """최소 필드로 ReportData를 생성할 수 있다"""
        from schemas.report import ReportData

        report = ReportData(
            branch_id=1,
            branch_name="테스트지점",
            affiliate_name="테스트업체",
            period_start="2024-01-01",
            period_end="2024-01-31",
        )

        assert report.branch_id == 1
        assert report.branch_name == "테스트지점"
        assert report.affiliate_name == "테스트업체"
        assert report.period_start == "2024-01-01"
        assert report.period_end == "2024-01-31"
        assert report.total_reviews == 0
        assert report.top_tags == []
        assert report.period_summary == ""

    def test_report_data_migrate_keywords(self):
        """top_keywords 필드는 top_tags로 마이그레이션된다"""
        from schemas.report import ReportData

        report = ReportData(
            branch_id=2,
            branch_name="구버전지점",
            affiliate_name="업체명",
            period_start="2023-06-01",
            period_end="2023-06-30",
            top_keywords=["친절", "청결", "가격"],  # type: ignore[call-arg]
        )

        assert report.top_tags == ["친절", "청결", "가격"]
        assert not hasattr(report, "top_keywords") or "top_keywords" not in report.model_dump()

    def test_report_data_model_dump(self):
        """model_dump()는 필요한 모든 키를 포함한 dict를 반환한다"""
        from schemas.report import ReportData

        report = ReportData(
            branch_id=3,
            branch_name="덤프지점",
            affiliate_name="덤프업체",
            period_start="2024-03-01",
            period_end="2024-03-31",
            total_reviews=75,
            top_tags=["친절", "청결"],
            period_summary="3월 리뷰 요약입니다.",
            generated_at="2024-04-01 10:00",
        )

        dumped = report.model_dump()

        assert isinstance(dumped, dict)
        assert dumped["branch_id"] == 3
        assert dumped["branch_name"] == "덤프지점"
        assert dumped["affiliate_name"] == "덤프업체"
        assert dumped["period_start"] == "2024-03-01"
        assert dumped["period_end"] == "2024-03-31"
        assert dumped["total_reviews"] == 75
        assert dumped["top_tags"] == ["친절", "청결"]
        assert dumped["period_summary"] == "3월 리뷰 요약입니다."
        assert dumped["generated_at"] == "2024-04-01 10:00"
        assert "strengths" in dumped
        assert "improvements" in dumped
        assert "vehicle_analysis" in dumped
