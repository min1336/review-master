"""ReportJobService 프로그레스 업데이트 테스트

progress_callback 호출 시 session.commit()이 실행되어
폴링 API에서 중간 진행률을 읽을 수 있는지 검증합니다.
"""

from __future__ import annotations

import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


class TestProgressCallbackCommit:
    """progress_callback 호출 시 session.commit() 동반 검증"""

    def _make_service(self):
        from services.report_job_service import ReportJobService

        return ReportJobService(
            job_repo=AsyncMock(),
            report_service=AsyncMock(),
        )

    @pytest.mark.asyncio
    async def test_progress_callback_commits_session(self):
        """progress_callback은 update_progress 후 session.commit()을 호출해야 한다"""
        # Arrange
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        mock_job_repo = AsyncMock()
        mock_job_repo.update_progress = AsyncMock(return_value=True)
        mock_job_repo.update_status = AsyncMock(return_value=True)

        mock_report_service = AsyncMock()

        # Capture the progress_callback when generate_report_with_progress is called
        captured_callback = None

        async def capture_callback(**kwargs):
            nonlocal captured_callback
            captured_callback = kwargs.get("progress_callback")
            # Simulate calling progress at 20%, 50%, 85%
            if captured_callback:
                await captured_callback(20)
                await captured_callback(50)
                await captured_callback(85)

        mock_report_service.generate_report_with_progress = capture_callback

        service = self._make_service()

        # Mock the session context manager
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory_fn = MagicMock(return_value=mock_ctx)

        with patch.object(service, '_create_job_repo', return_value=mock_job_repo), \
             patch.object(service, '_create_report_service', return_value=mock_report_service), \
             patch('repository.database.get_session_factory', return_value=mock_factory_fn):

            await service._run_job(
                job_id="test-job-1",
                branch_id=1,
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2024, 3, 31),
            )

        # Assert: progress_callback이 3회 호출됨
        assert mock_job_repo.update_progress.call_count == 3

        # Assert: session.commit()이 progress 호출마다 + 초기 processing + 최종 completed
        # 초기 processing commit(1) + progress 3회 commit(3) + 최종 completed commit(1) = 5회
        assert mock_session.commit.call_count >= 5, (
            f"session.commit()이 {mock_session.commit.call_count}회 호출됨. "
            "최소 5회 필요: initial(1) + progress(3) + final(1)."
        )

    @pytest.mark.asyncio
    async def test_initial_processing_status_commits(self):
        """초기 'processing' 상태 전환 후 commit이 호출되어야 한다"""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        mock_job_repo = AsyncMock()
        mock_job_repo.update_status = AsyncMock(return_value=True)
        mock_job_repo.update_progress = AsyncMock(return_value=True)

        mock_report_service = AsyncMock()
        mock_report_service.generate_report_with_progress = AsyncMock()

        service = self._make_service()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory_fn = MagicMock(return_value=mock_ctx)

        with patch.object(service, '_create_job_repo', return_value=mock_job_repo), \
             patch.object(service, '_create_report_service', return_value=mock_report_service), \
             patch('repository.database.get_session_factory', return_value=mock_factory_fn):

            await service._run_job(
                job_id="test-job-2",
                branch_id=1,
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2024, 3, 31),
            )

        # 최소 2회 commit: processing 전환 후 + completed 전환 후
        assert mock_session.commit.call_count >= 2, (
            f"commit {mock_session.commit.call_count}회 호출됨. "
            "최소 2회 필요: processing 전환 후 + completed 전환 후"
        )

    @pytest.mark.asyncio
    async def test_each_progress_update_triggers_commit(self):
        """각 progress_callback 호출이 개별 commit을 트리거하는지 검증"""
        mock_session = AsyncMock()
        mock_session.rollback = AsyncMock()
        commit_count_per_progress = []

        original_commit_count = 0

        async def tracking_commit():
            nonlocal original_commit_count
            original_commit_count += 1

        mock_session.commit = tracking_commit

        mock_job_repo = AsyncMock()
        mock_job_repo.update_status = AsyncMock(return_value=True)
        mock_job_repo.update_progress = AsyncMock(return_value=True)

        mock_report_service = AsyncMock()

        async def capture_and_track(**kwargs):
            cb = kwargs.get("progress_callback")
            if cb:
                before = original_commit_count
                await cb(25)
                commit_count_per_progress.append(original_commit_count - before)

                before = original_commit_count
                await cb(75)
                commit_count_per_progress.append(original_commit_count - before)

        mock_report_service.generate_report_with_progress = capture_and_track

        service = self._make_service()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory_fn = MagicMock(return_value=mock_ctx)

        with patch.object(service, '_create_job_repo', return_value=mock_job_repo), \
             patch.object(service, '_create_report_service', return_value=mock_report_service), \
             patch('repository.database.get_session_factory', return_value=mock_factory_fn):

            await service._run_job(
                job_id="test-job-3",
                branch_id=1,
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2024, 3, 31),
            )

        # 각 progress 호출마다 정확히 1회 commit이 발생해야 함
        for i, count in enumerate(commit_count_per_progress):
            assert count >= 1, (
                f"progress_callback #{i+1} 호출 후 commit이 {count}회 발생. "
                "각 progress 업데이트마다 최소 1회 commit 필요."
            )


class TestOrphanJobRecovery:
    """고아 작업 (processing 상태이지만 태스크 없음) 복구 검증"""

    def _make_service(self):
        from services.report_job_service import ReportJobService

        return ReportJobService(
            job_repo=AsyncMock(),
            report_service=AsyncMock(),
        )

    @pytest.mark.asyncio
    async def test_processing_orphan_job_restarts(self):
        """processing 상태이지만 _running_jobs에 없는 작업은 재시작되어야 한다"""
        service = self._make_service()

        # 기존 processing 상태의 고아 작업
        service.job_repo.get_active_by_branch_and_period = AsyncMock(return_value={
            "id": "orphan-job-1",
            "status": "processing",
            "branch_id": 1,
        })

        start = datetime(2024, 1, 1)
        end = datetime(2024, 3, 31)

        with patch.object(service, '_run_job', new_callable=AsyncMock) as mock_run:
            job_id = await service.submit_job(1, start, end)

        assert job_id == "orphan-job-1"
        # _run_job이 asyncio.create_task로 호출되었으므로 _running_jobs에 등록되어야 함
        assert "orphan-job-1" in service._running_jobs

    @pytest.mark.asyncio
    async def test_already_running_job_not_duplicated(self):
        """_running_jobs에 이미 있는 작업은 중복 시작하지 않아야 한다"""
        service = self._make_service()

        service.job_repo.get_active_by_branch_and_period = AsyncMock(return_value={
            "id": "running-job-1",
            "status": "processing",
            "branch_id": 1,
        })

        # 이미 실행 중인 태스크 시뮬레이션
        mock_task = MagicMock()
        mock_task.done.return_value = False
        service._running_jobs["running-job-1"] = mock_task

        start = datetime(2024, 1, 1)
        end = datetime(2024, 3, 31)

        with patch.object(service, '_run_job', new_callable=AsyncMock) as mock_run:
            job_id = await service.submit_job(1, start, end)

        assert job_id == "running-job-1"
        # _run_job이 호출되지 않아야 함 (이미 실행 중)
        mock_run.assert_not_called()
