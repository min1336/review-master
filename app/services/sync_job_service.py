"""동기화 비동기 작업 서비스

인메모리 싱글턴으로 sync 작업 상태를 추적한다.
sync는 전역 싱글턴 작업이므로 DB 테이블 불필요.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from core.timezone import utc_now
from schemas.sync import SyncJobStatusResponse, SyncResultResponse

logger = logging.getLogger(__name__)


@dataclass
class SyncJobState:
    """인메모리 작업 상태"""

    job_id: str
    status: str = "pending"  # pending | processing | completed | failed
    progress: int = 0
    message: str = ""
    error: str | None = None
    result: SyncResultResponse | None = None
    created_at: datetime = field(default_factory=utc_now)
    task: asyncio.Task[Any] | None = field(default=None, repr=False)


class SyncJobService:
    """동기화 비동기 작업 관리 (인메모리 싱글턴)"""

    _instance: SyncJobService | None = None
    _MAX_COMPLETED_JOBS = 5

    def __init__(self) -> None:
        self._jobs: dict[str, SyncJobState] = {}

    @classmethod
    def get_instance(cls) -> SyncJobService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def submit_job(self) -> SyncJobStatusResponse:
        """비동기 동기화 작업 제출

        이미 활성 작업이 있으면 기존 job_id를 반환한다.
        """
        # 이미 실행 중인 작업이 있는 경우
        for job in self._jobs.values():
            if job.status in ("pending", "processing"):
                return self._to_response(job)

        self._prune_old_jobs()

        job_id = uuid4().hex[:12]
        state = SyncJobState(job_id=job_id)
        self._jobs[job_id] = state

        task = asyncio.create_task(self._run_job(state))
        state.task = task

        return self._to_response(state)

    def get_job_status(self, job_id: str) -> SyncJobStatusResponse | None:
        """작업 상태 조회 (DB 접근 없음)"""
        state = self._jobs.get(job_id)
        if state is None:
            return None
        return self._to_response(state)

    async def cancel_job(self, job_id: str) -> bool:
        """작업 취소"""
        state = self._jobs.get(job_id)
        if state is None:
            return False

        if state.task and not state.task.done():
            state.task.cancel()
            state.status = "failed"
            state.error = "사용자에 의해 취소됨"
            logger.info(f"동기화 작업 취소: {job_id}")
            return True

        return False

    def _prune_old_jobs(self) -> None:
        """완료/실패 작업이 _MAX_COMPLETED_JOBS를 초과하면 오래된 것부터 제거"""
        done = [
            s for s in self._jobs.values()
            if s.status in ("completed", "failed")
        ]
        if len(done) <= self._MAX_COMPLETED_JOBS:
            return
        done.sort(key=lambda s: s.created_at)
        for s in done[: len(done) - self._MAX_COMPLETED_JOBS]:
            self._jobs.pop(s.job_id, None)

    async def _run_job(self, state: SyncJobState) -> None:
        """백그라운드에서 동기화 실행"""
        try:
            state.status = "processing"
            state.progress = 0
            state.message = "동기화 준비 중"

            async def progress_callback(progress: int, message: str) -> None:
                state.progress = progress
                state.message = message

            # SyncService 인스턴스 생성
            from infrastructure.athena import AthenaClient
            from repository.database import get_session_factory
            from repository.review_repository import BranchReviewRepository
            from services.sync_service import SyncService

            session = get_session_factory()()
            try:
                review_repo = BranchReviewRepository(session)

                athena_client: AthenaClient | None = None
                try:
                    from core.config import get_settings

                    settings = get_settings()
                    if settings.aws_access_key_id and settings.athena_output_bucket:
                        athena_client = AthenaClient()
                except Exception as e:
                    logger.debug(f"Athena 클라이언트 초기화 스킵: {e}")

                sync_service = SyncService(review_repo, athena_client)

                result = await sync_service.sync_reviews(progress_callback=progress_callback)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

            state.status = "completed"
            state.progress = 100
            state.message = result.message
            state.result = result
            logger.info(f"동기화 작업 완료: {state.job_id}")

        except asyncio.CancelledError:
            state.status = "failed"
            state.error = "작업이 취소되었습니다"
            logger.info(f"동기화 작업 취소됨: {state.job_id}")
        except Exception as e:
            state.status = "failed"
            state.error = str(e)
            state.message = "동기화 중 오류 발생"
            logger.exception(f"동기화 작업 실패: {state.job_id}")

    @staticmethod
    def _to_response(state: SyncJobState) -> SyncJobStatusResponse:
        return SyncJobStatusResponse(
            job_id=state.job_id,
            status=state.status,
            progress=state.progress,
            message=state.message,
            error=state.error,
            result=state.result,
            created_at=state.created_at,
        )
