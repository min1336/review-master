"""SyncJobService 좀비 작업 자동 만료 + status 전환 안전화 검증 (❶❷)

수정 내용:
- submit_job(): task.done() 또는 300초 초과 시 좀비 작업 자동 만료 후 새 작업 생성
- _run_job(): status="processing"이 try 블록 밖에서 설정, BaseException 캐치
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.sync_job_service import SyncJobService, SyncJobState, _JOB_STALE_TIMEOUT_SECONDS


# ============================================================
# V-001: 좀비 작업 자동 만료
# ============================================================


class TestStaleJobDetection:
    """submit_job()에서 좀비 작업 감지 및 자동 만료 테스트"""

    def _make_service(self) -> SyncJobService:
        """테스트용 독립 인스턴스 (싱글턴 우회)"""
        svc = SyncJobService.__new__(SyncJobService)
        svc._jobs = {}
        return svc

    @pytest.mark.asyncio
    async def test_dead_task_pending_is_expired(self):
        """task.done()=True인 pending 작업 → 자동 만료 후 새 job_id 반환"""
        svc = self._make_service()

        # 이전에 pending 상태에서 task가 죽은 작업 생성
        dead_task = asyncio.ensure_future(asyncio.sleep(0))
        await dead_task  # task 완료 → done() = True

        old_state = SyncJobState(
            job_id="dead_job_001",
            status="pending",
            task=dead_task,
        )
        svc._jobs["dead_job_001"] = old_state

        # submit_job 호출 → 새 작업이 생성되어야 함
        with patch("services.sync_job_service.SyncJobService._run_job", new_callable=AsyncMock):
            result = await svc.submit_job()

        assert result.job_id != "dead_job_001", "죽은 작업 대신 새 작업이 생성되어야 함"
        assert old_state.status == "failed", "죽은 작업의 status가 failed로 전환되어야 함"
        assert old_state.error == "작업이 비정상 종료되었습니다"

    @pytest.mark.asyncio
    async def test_stale_processing_job_is_expired(self):
        """300초 초과된 processing 작업 → 자동 만료 후 새 job_id 반환"""
        svc = self._make_service()

        # 300초 이상 전에 생성된 processing 작업 (task는 아직 살아있음)
        stale_task = asyncio.ensure_future(asyncio.sleep(9999))

        old_state = SyncJobState(
            job_id="stale_job_001",
            status="processing",
            task=stale_task,
            created_at=datetime.now(timezone.utc) - timedelta(seconds=_JOB_STALE_TIMEOUT_SECONDS + 60),
        )
        svc._jobs["stale_job_001"] = old_state

        with patch("services.sync_job_service.SyncJobService._run_job", new_callable=AsyncMock):
            result = await svc.submit_job()

        assert result.job_id != "stale_job_001", "타임아웃된 작업 대신 새 작업이 생성되어야 함"
        assert old_state.status == "failed", "타임아웃된 작업의 status가 failed로 전환되어야 함"
        assert "시간 초과" in old_state.error

        # 정리
        stale_task.cancel()
        try:
            await stale_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_active_job_returns_existing(self):
        """정상 실행 중인 작업이 있을 때 → 기존 job_id 반환"""
        svc = self._make_service()

        # 최근에 생성된 정상 processing 작업
        active_task = asyncio.ensure_future(asyncio.sleep(9999))

        active_state = SyncJobState(
            job_id="active_job_001",
            status="processing",
            task=active_task,
            created_at=datetime.now(timezone.utc) - timedelta(seconds=10),  # 10초 전
        )
        svc._jobs["active_job_001"] = active_state

        result = await svc.submit_job()

        assert result.job_id == "active_job_001", "정상 실행 중인 작업의 job_id를 반환해야 함"
        assert active_state.status == "processing", "정상 작업의 status는 변경되지 않아야 함"

        # 정리
        active_task.cancel()
        try:
            await active_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_dead_task_with_none_task(self):
        """task가 None인 pending 작업 → 자동 만료"""
        svc = self._make_service()

        old_state = SyncJobState(
            job_id="null_task_001",
            status="pending",
            task=None,  # task가 설정되지 않음
        )
        svc._jobs["null_task_001"] = old_state

        with patch("services.sync_job_service.SyncJobService._run_job", new_callable=AsyncMock):
            result = await svc.submit_job()

        assert result.job_id != "null_task_001"
        assert old_state.status == "failed"


# ============================================================
# V-002: status 전환 안전화 + BaseException 캐치
# ============================================================


class TestStatusTransitionSafety:
    """_run_job()의 status 전환이 try 블록 밖에서 일어나고 모든 예외를 캐치하는지 검증"""

    def _make_service(self) -> SyncJobService:
        svc = SyncJobService.__new__(SyncJobService)
        svc._jobs = {}
        return svc

    @pytest.mark.asyncio
    async def test_status_set_to_processing_before_try(self):
        """_run_job 진입 시 즉시 status='processing' 설정"""
        svc = self._make_service()
        state = SyncJobState(job_id="test_001", status="pending")

        # _run_job 내부의 로컬 import를 패치 (repository.database 모듈 레벨)
        with patch("repository.database.get_session_factory", side_effect=RuntimeError("DB 연결 실패")):
            await svc._run_job(state)

        # status가 "pending"이 아닌지 확인 (processing → failed 경로)
        assert state.status == "failed", "예외 발생 시 status가 failed여야 함 (pending에 머물면 안 됨)"
        assert state.error is not None

    @pytest.mark.asyncio
    async def test_base_exception_is_caught(self):
        """RuntimeError 등 BaseException 서브클래스도 캐치됨"""
        svc = self._make_service()
        state = SyncJobState(job_id="test_002", status="pending")

        with patch("repository.database.get_session_factory", side_effect=RuntimeError("치명적 오류")):
            await svc._run_job(state)

        assert state.status == "failed"
        assert "치명적 오류" in state.error

    @pytest.mark.asyncio
    async def test_cancelled_error_sets_failed(self):
        """asyncio.CancelledError 발생 시 status='failed'"""
        svc = self._make_service()
        state = SyncJobState(job_id="test_003", status="pending")

        with patch("repository.database.get_session_factory", side_effect=asyncio.CancelledError()):
            await svc._run_job(state)

        assert state.status == "failed"
        assert "취소" in state.error
