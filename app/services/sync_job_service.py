"""동기화 비동기 작업 서비스

인메모리 싱글턴으로 sync 작업 상태를 추적한다.
sync는 전역 싱글턴 작업이므로 DB 테이블 불필요.
"""

from __future__ import annotations

import asyncio
import gc
import logging
from dataclasses import dataclass, field

from core.timezone import utc_now
from schemas.sync import SyncJobStatusResponse, SyncResultResponse
from services.base_job_service import BaseJobService, BaseJobState

logger = logging.getLogger(__name__)

# 작업 TTL: 이 시간 초과 시 좀비 작업으로 간주하고 자동 만료 (초)
_JOB_STALE_TIMEOUT_SECONDS = 300


@dataclass
class SyncJobState(BaseJobState):
    """인메모리 작업 상태"""

    result: SyncResultResponse | None = field(default=None)


class SyncJobService(BaseJobService[SyncJobState, SyncJobStatusResponse]):
    """동기화 비동기 작업 관리 (인메모리 싱글턴)"""

    async def submit_job(
        self,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> SyncJobStatusResponse:
        """비동기 동기화 작업 제출

        이미 활성 작업이 있으면 기존 job_id를 반환한다.

        Args:
            date_from: 시작일 (YYYY-MM-DD). None이면 last_sync_at 기준.
            date_to: 종료일 (YYYY-MM-DD). None이면 제한 없음.
        """
        # 이미 실행 중인 작업이 있는 경우 (좀비 작업 감지 포함)
        active = self._find_active_job()
        if active is not None:
            elapsed = (utc_now() - active.last_activity_at).total_seconds()
            task_dead = active.task is None or active.task.done()

            if task_dead or elapsed > _JOB_STALE_TIMEOUT_SECONDS:
                active.status = "failed"
                if task_dead:
                    active.error = "작업이 비정상 종료되었습니다"
                else:
                    active.error = f"작업 시간 초과 ({int(elapsed)}초)"
                    if active.task:
                        active.task.cancel()
                logger.warning(
                    "Stale sync job expired: %s (elapsed=%.0fs, task_dead=%s)",
                    active.job_id, elapsed, task_dead,
                )
            else:
                return self._to_response(active)

        self._prune_old_jobs()

        job_id = self._generate_job_id()
        state = SyncJobState(job_id=job_id)
        self._jobs[job_id] = state

        task = asyncio.create_task(self._run_job(state, date_from, date_to))
        state.task = task

        return self._to_response(state)

    async def _run_job(
        self,
        state: SyncJobState,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> None:
        """백그라운드에서 동기화 실행"""
        state.status = "processing"
        state.progress = 0
        state.message = "동기화 준비 중"
        try:
            async def progress_callback(progress: int, message: str) -> None:
                state.progress = progress
                state.message = message
                state.last_activity_at = utc_now()

            # SyncService 인스턴스 생성
            # NOTE: NLP 모델은 서버 시작 시 _prewarm_nlp_models()에서 미리 로드되므로
            # 여기서는 동기 생성해도 이벤트 루프 블로킹 없음.
            # asyncio.to_thread 래핑 시 threading.Lock 경합으로 이벤트 루프 데드락 위험.
            from core.container import ServiceContainer
            from repository.database import get_session_factory
            from repository.review_repository import BranchReviewRepository
            from services.sync_service import SyncService

            athena_client = ServiceContainer.get_athena_client()

            factory = get_session_factory()
            async with factory() as session:
                try:
                    review_repo = BranchReviewRepository(session)
                    sync_service = SyncService(review_repo, athena_client)

                    result = await sync_service.sync_reviews(
                        progress_callback=progress_callback,
                        date_from=date_from,
                        date_to=date_to,
                    )
                    await session.commit()
                    gc.collect()
                except Exception:
                    await session.rollback()
                    raise

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

    def _to_response(self, state: SyncJobState) -> SyncJobStatusResponse:
        return SyncJobStatusResponse(
            job_id=state.job_id,
            status=state.status,
            progress=state.progress,
            message=state.message,
            error=state.error,
            result=state.result,
            created_at=state.created_at,
        )
