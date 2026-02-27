"""파이프라인 전체 재처리 비동기 작업 서비스

인메모리 싱글턴으로 전체 재처리 작업 상태를 추적한다.
SyncJobService 패턴을 재사용하되, DB 기반 리뷰 로드 + 청크 실행을 수행한다.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from core.timezone import utc_now
from schemas.pipeline_console import PipelineJobStatusResponse

logger = logging.getLogger(__name__)

PIPELINE_CHUNK_DEFAULT = 500


@dataclass
class PipelineJobState:
    """인메모리 파이프라인 작업 상태"""

    job_id: str
    status: str = "pending"  # pending | processing | completed | failed
    progress: int = 0
    message: str = ""
    total_reviews: int = 0
    processed_reviews: int = 0
    current_chunk: int = 0
    total_chunks: int = 0
    error: str | None = None
    result: dict | None = None
    created_at: datetime = field(default_factory=utc_now)
    task: asyncio.Task[Any] | None = field(default=None, repr=False)


class PipelineJobService:
    """전체 재처리 파이프라인 비동기 작업 관리 (인메모리 싱글턴)"""

    _instance: PipelineJobService | None = None
    _MAX_COMPLETED_JOBS = 5

    def __init__(self) -> None:
        self._jobs: dict[str, PipelineJobState] = {}

    @classmethod
    def get_instance(cls) -> PipelineJobService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def submit_job(
        self,
        date_from: str | None = None,
        date_to: str | None = None,
        chunk_size: int = PIPELINE_CHUNK_DEFAULT,
    ) -> PipelineJobStatusResponse:
        """비동기 전체 재처리 작업 제출.

        자기 자신 및 다른 파이프라인 서비스(sync, upload)에 활성 작업이 있으면 거부한다.
        """
        # 자기 자신의 활성 작업 확인
        for job in self._jobs.values():
            if job.status in ("pending", "processing"):
                return self._to_response(job)

        # 상호 배제: 다른 파이프라인 작업 확인
        self._check_other_pipelines()

        self._prune_old_jobs()

        job_id = uuid4().hex[:12]
        state = PipelineJobState(job_id=job_id)
        self._jobs[job_id] = state

        task = asyncio.create_task(
            self._run_job(state, date_from, date_to, chunk_size)
        )
        state.task = task

        logger.info(
            "파이프라인 작업 제출: job_id=%s, date_from=%s, date_to=%s, chunk=%d",
            job_id, date_from, date_to, chunk_size,
        )
        return self._to_response(state)

    def get_job_status(self, job_id: str) -> PipelineJobStatusResponse | None:
        """작업 상태 조회"""
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
            logger.info("파이프라인 작업 취소: %s", job_id)
            return True

        return False

    def _check_other_pipelines(self) -> None:
        """다른 파이프라인 서비스에 활성 작업이 있으면 HTTPException 발생"""
        from fastapi import HTTPException

        from services.sync_job_service import SyncJobService
        from services.upload_job_service import UploadJobService

        sync_svc = SyncJobService.get_instance()
        for job in sync_svc._jobs.values():
            if job.status in ("pending", "processing"):
                raise HTTPException(409, "동기화 작업이 실행 중입니다")

        upload_svc = UploadJobService.get_instance()
        for job in upload_svc._jobs.values():
            if job.status in ("pending", "processing"):
                raise HTTPException(409, "업로드 작업이 실행 중입니다")

    def _prune_old_jobs(self) -> None:
        """완료/실패 작업이 초과하면 오래된 것부터 제거"""
        done = [s for s in self._jobs.values() if s.status in ("completed", "failed")]
        if len(done) <= self._MAX_COMPLETED_JOBS:
            return
        done.sort(key=lambda s: s.created_at)
        for s in done[: len(done) - self._MAX_COMPLETED_JOBS]:
            self._jobs.pop(s.job_id, None)

    async def _run_job(
        self,
        state: PipelineJobState,
        date_from: str | None,
        date_to: str | None,
        chunk_size: int,
    ) -> None:
        """백그라운드에서 전체 재처리 파이프라인 실행"""
        start = time.time()
        try:
            state.status = "processing"
            state.progress = 5
            state.message = "리뷰 조회 준비 중"

            from domain.pipeline.unified_pipeline import UnifiedPipeline
            from repository.database import get_session_factory
            from repository.review_repository import BranchReviewRepository

            # --- Phase 1: 전체 리뷰 카운트 조회 ---
            session = get_session_factory()()
            try:
                review_repo = BranchReviewRepository(session)
                count_result = await review_repo.search_with_filters(
                    date_from=date_from,
                    date_to=date_to,
                    limit=0,
                    offset=0,
                )
                total = count_result.total
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

            if total == 0:
                state.status = "completed"
                state.progress = 100
                state.message = "처리할 리뷰가 없습니다"
                state.result = {"processed": 0, "total": 0}
                return

            state.total_reviews = total
            total_chunks = (total + chunk_size - 1) // chunk_size
            state.total_chunks = total_chunks
            state.progress = 10
            state.message = f"총 {total}건 리뷰, {total_chunks}개 청크로 분할 처리"

            # --- Phase 2: 청크별 로드 + 파이프라인 실행 ---
            pipeline = UnifiedPipeline()
            total_processed = 0

            for chunk_idx in range(total_chunks):
                offset = chunk_idx * chunk_size
                state.current_chunk = chunk_idx + 1

                # 청크별 새 세션으로 리뷰 로드
                session = get_session_factory()()
                try:
                    review_repo = BranchReviewRepository(session)
                    chunk_result = await review_repo.search_with_filters(
                        date_from=date_from,
                        date_to=date_to,
                        limit=chunk_size,
                        offset=offset,
                    )
                    reviews = chunk_result.reviews

                    # 데드락 방지: 로드 세션 커밋 후 닫기
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise
                finally:
                    await session.close()

                if not reviews:
                    break

                # 파이프라인 실행 (자체 세션 사용)
                result = await pipeline.run(reviews)
                total_processed += result.processed_reviews
                state.processed_reviews = total_processed

                # 진행률: 10% (준비) ~ 95% (파이프라인)
                pct = 10 + int(min(offset + chunk_size, total) / total * 85)
                state.progress = pct
                state.message = (
                    f"분석 중 ({chunk_idx + 1}/{total_chunks} 청크, "
                    f"{total_processed}/{total}건 처리)"
                )

            # --- 완료 ---
            duration = time.time() - start
            state.status = "completed"
            state.progress = 100
            state.message = f"전체 재처리 완료: {total_processed}/{total}건"
            state.result = {
                "processed": total_processed,
                "total": total,
                "chunks": total_chunks,
                "duration_seconds": round(duration, 1),
            }
            logger.info(
                "파이프라인 작업 완료: job=%s, processed=%d/%d, %.1fs",
                state.job_id, total_processed, total, duration,
            )

        except asyncio.CancelledError:
            state.status = "failed"
            state.error = "작업이 취소되었습니다"
            logger.info("파이프라인 작업 취소됨: %s", state.job_id)
        except Exception as e:
            state.status = "failed"
            state.error = str(e)
            state.message = "파이프라인 처리 중 오류 발생"
            logger.exception("파이프라인 작업 실패: %s", state.job_id)

    @staticmethod
    def _to_response(state: PipelineJobState) -> PipelineJobStatusResponse:
        return PipelineJobStatusResponse(
            job_id=state.job_id,
            status=state.status,
            progress=state.progress,
            message=state.message,
            total_reviews=state.total_reviews,
            processed_reviews=state.processed_reviews,
            current_chunk=state.current_chunk,
            total_chunks=state.total_chunks,
            error=state.error,
            result=state.result,
            created_at=state.created_at,
        )
