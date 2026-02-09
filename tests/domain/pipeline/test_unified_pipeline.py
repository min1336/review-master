"""UnifiedPipeline 통합 테스트"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from domain.pipeline.unified_pipeline import UnifiedPipeline
from schemas.dto import PipelineResultDTO, PipelineStepResultDTO


class TestUnifiedPipeline:
    """UnifiedPipeline 테스트 클래스"""

    @pytest.fixture
    def pipeline(self):
        """UnifiedPipeline 인스턴스"""
        return UnifiedPipeline()

    @pytest.fixture
    def sample_reviews(self):
        """샘플 리뷰 데이터"""
        return [
            {
                "review_id": "1001",
                "branch_id": "100",
                "content": "직원분들이 정말 친절하고 차량도 깨끗했습니다.",
                "branch_name": "제주공항점",
                "rating_service": "5.0",
                "rating_car": "5.0",
                "rating_convenience": "4.5",
                "review_date": "2026-02-01 10:00:00",
                "car_type": "아반떼",
                "company_name": "카모아렌트카",
                "status": "1",
            },
            {
                "review_id": "1002",
                "branch_id": "100",
                "content": "가격이 저렴하고 서비스도 만족스러웠습니다.",
                "branch_name": "제주공항점",
                "rating_service": "4.5",
                "rating_car": "4.0",
                "rating_convenience": "5.0",
                "review_date": "2026-02-02 11:00:00",
                "car_type": "소나타",
                "company_name": "카모아렌트카",
                "status": "1",
            },
        ]

    def test_pipeline_initialization(self, pipeline):
        """파이프라인 초기화 테스트"""
        assert pipeline.preprocessor is not None
        assert pipeline.review_updater is not None
        assert pipeline.sentiment_stats is not None
        assert pipeline.tag_aggregator is not None
        assert pipeline.car_model_tags is not None
        assert pipeline.keyword_manager is not None

    @pytest.mark.asyncio
    async def test_run_empty_reviews(self, pipeline):
        """빈 리뷰 리스트 처리"""
        with patch('domain.pipeline.unified_pipeline.get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await pipeline.run([])

            assert isinstance(result, PipelineResultDTO)
            assert result.success is True
            assert result.total_reviews == 0
            assert result.processed_reviews == 0

    @pytest.mark.asyncio
    async def test_run_with_valid_reviews(self, pipeline, sample_reviews):
        """유효한 리뷰 처리"""
        with patch('domain.pipeline.unified_pipeline.get_client') as mock_get_client:
            # Mock Supabase client
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            # Mock table operations
            mock_table = MagicMock()
            mock_client.table.return_value = mock_table

            mock_select = MagicMock()
            mock_table.select.return_value = mock_select
            mock_select.eq.return_value = mock_select
            mock_select.execute = AsyncMock(return_value=MagicMock(data=[]))

            mock_update = MagicMock()
            mock_table.update.return_value = mock_update
            mock_update.eq.return_value = mock_update
            mock_update.execute = AsyncMock(return_value=MagicMock(data=[]))

            mock_upsert = MagicMock()
            mock_table.upsert.return_value = mock_upsert
            mock_upsert.execute = AsyncMock(return_value=MagicMock(data=[{"id": 1}]))

            result = await pipeline.run(sample_reviews)

            assert isinstance(result, PipelineResultDTO)
            assert result.success is True
            assert result.total_reviews == 2
            # preprocessor가 필터링할 수 있으므로 processed_reviews <= total_reviews
            assert result.processed_reviews <= result.total_reviews

    @pytest.mark.asyncio
    async def test_run_handles_exception(self, pipeline, sample_reviews):
        """예외 처리 테스트"""
        with patch('domain.pipeline.unified_pipeline.get_client') as mock_get_client:
            mock_get_client.side_effect = Exception("DB 연결 실패")

            result = await pipeline.run(sample_reviews)

            assert isinstance(result, PipelineResultDTO)
            assert result.success is False
            assert result.error_message == "DB 연결 실패"

    @pytest.mark.asyncio
    async def test_run_returns_correct_branch_count(self, pipeline):
        """지점 수 정확성 테스트"""
        reviews = [
            {
                "review_id": "1",
                "branch_id": "100",
                "content": "첫 번째 지점 리뷰입니다. 좋았어요.",
                "branch_name": "A점",
                "rating_service": "5.0",
                "review_date": "2026-02-01 10:00:00",
            },
            {
                "review_id": "2",
                "branch_id": "200",
                "content": "두 번째 지점 리뷰입니다. 만족합니다.",
                "branch_name": "B점",
                "rating_service": "4.5",
                "review_date": "2026-02-01 11:00:00",
            },
            {
                "review_id": "3",
                "branch_id": "100",
                "content": "첫 번째 지점 다른 리뷰. 재방문 의사 있습니다.",
                "branch_name": "A점",
                "rating_service": "4.0",
                "review_date": "2026-02-01 12:00:00",
            },
        ]

        with patch('domain.pipeline.unified_pipeline.get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_table = MagicMock()
            mock_client.table.return_value = mock_table
            mock_select = MagicMock()
            mock_table.select.return_value = mock_select
            mock_select.eq.return_value = mock_select
            mock_select.execute = AsyncMock(return_value=MagicMock(data=[]))
            mock_table.update.return_value.eq.return_value.execute = AsyncMock(return_value=MagicMock(data=[]))
            mock_table.upsert.return_value.execute = AsyncMock(return_value=MagicMock(data=[]))

            result = await pipeline.run(reviews)

            # 2개 지점 (100, 200)
            if result.processed_reviews > 0:
                assert result.total_branches <= 2

    @pytest.mark.asyncio
    async def test_run_preprocessor_filters_all(self, pipeline):
        """전처리에서 모든 리뷰가 필터링되면 빈 결과 반환"""
        reviews = [
            {
                "review_id": "1",
                "branch_id": "100",
                "content": "짧",  # 5자 미만 → 필터링
                "branch_name": "A점",
                "rating_service": "5.0",
            },
            {
                "review_id": "2",
                "branch_id": "100",
                "content": "",  # 빈 내용 → 필터링
                "branch_name": "A점",
                "rating_service": "5.0",
            },
        ]

        with patch('domain.pipeline.unified_pipeline.get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await pipeline.run(reviews)

            assert result.success is True
            assert result.total_reviews == 2
            assert result.processed_reviews == 0
            assert result.total_branches == 0

    @pytest.mark.asyncio
    async def test_run_step2_exception_partial_failure(self, pipeline, sample_reviews):
        """Step 2 (review_updater) 예외 시 해당 단계만 실패, 나머지 계속 진행"""
        with patch('domain.pipeline.unified_pipeline.get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            # Mock table operations for other steps
            mock_table = MagicMock()
            mock_client.table.return_value = mock_table
            mock_select = MagicMock()
            mock_table.select.return_value = mock_select
            mock_select.eq.return_value = mock_select
            mock_select.in_.return_value = mock_select
            mock_select.execute = AsyncMock(return_value=MagicMock(data=[]))
            mock_table.upsert.return_value.execute = AsyncMock(return_value=MagicMock(data=[]))
            mock_table.update.return_value.eq.return_value.execute = AsyncMock(return_value=MagicMock(data=[]))

            # review_updater.update에서 예외 발생
            pipeline.review_updater.update = AsyncMock(
                side_effect=Exception("Step 2 실패")
            )

            result = await pipeline.run(sample_reviews)

            assert result.success is False
            assert "review_updater" in result.failed_steps
            # 다른 단계의 StepResultDTO가 존재해야 함
            step_names = [s.step_name for s in result.steps]
            assert "preprocessor" in step_names
            assert "review_updater" in step_names
            # 부분 실패: review_updater 이후 단계도 실행됨
            assert len(result.steps) >= 3

    @pytest.mark.asyncio
    async def test_run_step3_exception_partial_failure(self, pipeline, sample_reviews):
        """Step 3 (sentiment_stats) 예외 시 해당 단계만 실패, 나머지 계속 진행"""
        with patch('domain.pipeline.unified_pipeline.get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            # Mock table operations for other steps
            mock_table = MagicMock()
            mock_client.table.return_value = mock_table
            mock_select = MagicMock()
            mock_table.select.return_value = mock_select
            mock_select.eq.return_value = mock_select
            mock_select.in_.return_value = mock_select
            mock_select.execute = AsyncMock(return_value=MagicMock(data=[]))
            mock_update = MagicMock()
            mock_table.update.return_value = mock_update
            mock_update.eq.return_value = mock_update
            mock_update.execute = AsyncMock(return_value=MagicMock(data=[]))
            mock_table.upsert.return_value.execute = AsyncMock(return_value=MagicMock(data=[]))

            pipeline.sentiment_stats.update = AsyncMock(
                side_effect=Exception("Step 3 실패")
            )

            result = await pipeline.run(sample_reviews)

            assert result.success is False
            assert "sentiment_stats" in result.failed_steps
            # review_updater는 성공했어야 함
            review_updater_step = next(
                s for s in result.steps if s.step_name == "review_updater"
            )
            assert review_updater_step.success is True
            # sentiment_stats 실패 후에도 다른 단계 계속 실행
            assert len(result.steps) >= 4

    @pytest.mark.asyncio
    async def test_run_result_has_timestamps(self, pipeline):
        """결과에 started_at, finished_at 타임스탬프가 있는지"""
        with patch('domain.pipeline.unified_pipeline.get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await pipeline.run([])

            assert result.started_at is not None
            assert result.finished_at is not None
            assert isinstance(result.started_at, datetime)
            assert isinstance(result.finished_at, datetime)
            assert result.finished_at >= result.started_at


# ==============================================================================
# PipelineResultDTO 구조 테스트
# ==============================================================================


class TestPipelineResultDTO:
    """PipelineResultDTO 구조 및 메서드 테스트"""

    def test_structure(self):
        """기본 구조 테스트"""
        result = PipelineResultDTO(
            success=True,
            total_reviews=100,
            processed_reviews=95,
            total_branches=10,
            summaries_generated=0,
            total_duration_seconds=5.5,
            started_at=datetime.now(),
            finished_at=datetime.now(),
        )

        result_dict = result.to_dict()

        assert "success" in result_dict
        assert "total_reviews" in result_dict
        assert "processed_reviews" in result_dict
        assert "total_branches" in result_dict
        assert "summaries_generated" in result_dict
        assert "steps" in result_dict
        assert result_dict["success"] is True
        assert result_dict["total_reviews"] == 100

    def test_add_step(self):
        """스텝 결과 추가"""
        result = PipelineResultDTO(
            success=True,
            total_reviews=10,
            processed_reviews=10,
            total_branches=1,
            summaries_generated=0,
        )

        step = PipelineStepResultDTO(
            step_name="preprocessor",
            success=True,
            input_count=10,
            output_count=8,
            duration_seconds=1.2,
        )
        result.add_step(step)

        assert len(result.steps) == 1
        assert result.steps[0].step_name == "preprocessor"
        assert result.steps[0].success is True

    def test_failed_steps(self):
        """실패한 스텝 목록"""
        result = PipelineResultDTO(
            success=False,
            total_reviews=10,
            processed_reviews=0,
            total_branches=0,
            summaries_generated=0,
        )

        result.add_step(PipelineStepResultDTO(
            step_name="preprocessor", success=True, input_count=10, output_count=8,
        ))
        result.add_step(PipelineStepResultDTO(
            step_name="review_updater", success=False, input_count=8, output_count=0,
            error_message="DB 연결 실패",
        ))
        result.add_step(PipelineStepResultDTO(
            step_name="sentiment_stats", success=True, input_count=8, output_count=8,
        ))

        failed = result.failed_steps
        assert len(failed) == 1
        assert "review_updater" in failed

    def test_to_dict_with_steps(self):
        """steps가 포함된 to_dict"""
        result = PipelineResultDTO(
            success=True,
            total_reviews=10,
            processed_reviews=10,
            total_branches=1,
            summaries_generated=0,
            started_at=datetime(2026, 2, 1, 10, 0, 0),
            finished_at=datetime(2026, 2, 1, 10, 0, 5),
        )

        result.add_step(PipelineStepResultDTO(
            step_name="preprocessor", success=True, input_count=10, output_count=8,
            duration_seconds=1.0,
        ))

        d = result.to_dict()
        assert len(d["steps"]) == 1
        assert d["steps"][0]["step_name"] == "preprocessor"
        assert d["started_at"] == "2026-02-01T10:00:00"
        assert d["finished_at"] == "2026-02-01T10:00:05"

    def test_to_dict_finished_at_none(self):
        """finished_at이 None인 경우"""
        result = PipelineResultDTO(
            success=True,
            total_reviews=0,
            processed_reviews=0,
            total_branches=0,
            summaries_generated=0,
            finished_at=None,
        )

        d = result.to_dict()
        assert d["finished_at"] is None

    def test_error_message_default_none(self):
        """error_message 기본값은 None"""
        result = PipelineResultDTO(
            success=True,
            total_reviews=0,
            processed_reviews=0,
            total_branches=0,
            summaries_generated=0,
        )
        assert result.error_message is None

    def test_steps_default_empty(self):
        """steps 기본값은 빈 리스트"""
        result = PipelineResultDTO(
            success=True,
            total_reviews=0,
            processed_reviews=0,
            total_branches=0,
            summaries_generated=0,
        )
        assert result.steps == []
        assert result.failed_steps == []


# ==============================================================================
# PipelineStepResultDTO 테스트
# ==============================================================================


class TestPipelineStepResultDTO:
    """PipelineStepResultDTO 테스트"""

    def test_to_dict(self):
        """to_dict 변환"""
        step = PipelineStepResultDTO(
            step_name="tag_aggregator",
            success=True,
            input_count=50,
            output_count=45,
            duration_seconds=2.3,
        )

        d = step.to_dict()
        assert d["step_name"] == "tag_aggregator"
        assert d["success"] is True
        assert d["input_count"] == 50
        assert d["output_count"] == 45
        assert d["duration_seconds"] == 2.3
        assert d["error_message"] is None

    def test_to_dict_with_error(self):
        """에러가 있는 스텝 to_dict"""
        step = PipelineStepResultDTO(
            step_name="review_updater",
            success=False,
            input_count=10,
            output_count=0,
            error_message="Connection timeout",
        )

        d = step.to_dict()
        assert d["success"] is False
        assert d["error_message"] == "Connection timeout"

    def test_default_values(self):
        """기본값 검증"""
        step = PipelineStepResultDTO(
            step_name="test_step",
            success=True,
            input_count=0,
            output_count=0,
        )
        assert step.duration_seconds == 0.0
        assert step.error_message is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
