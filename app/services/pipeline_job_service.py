"""파이프라인 전체 재처리 비동기 작업 서비스

인메모리 싱글턴으로 전체 재처리 작업 상태를 추적한다.
SyncJobService 패턴을 재사용하되, DB 기반 리뷰 로드 + 청크 실행을 수행한다.
"""

from __future__ import annotations

import asyncio
import gc
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from schemas.pipeline_console import PipelineJobStatusResponse
from services.base_job_service import BaseJobService, BaseJobState

logger = logging.getLogger(__name__)

PIPELINE_CHUNK_DEFAULT = 500


@dataclass
class PipelineJobState(BaseJobState):
    """인메모리 파이프라인 작업 상태"""

    total_reviews: int = 0
    processed_reviews: int = 0
    current_chunk: int = 0
    total_chunks: int = 0
    result: dict | None = None


class PipelineJobService(BaseJobService[PipelineJobState, PipelineJobStatusResponse]):
    """전체 재처리 파이프라인 비동기 작업 관리 (인메모리 싱글턴)"""

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
        active = self._find_active_job()
        if active:
            return self._to_response(active)

        # 상호 배제: 다른 파이프라인 작업 확인
        self._check_other_pipelines()

        self._prune_old_jobs()

        job_id = self._generate_job_id()
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

    def _check_other_pipelines(self) -> None:
        """다른 파이프라인 서비스에 활성 작업이 있으면 HTTPException 발생"""
        from fastapi import HTTPException

        from services.sync_job_service import SyncJobService
        from services.upload_job_service import UploadJobService

        sync_svc = SyncJobService.get_instance()
        if sync_svc.has_active_job():
            raise HTTPException(409, "동기화 작업이 실행 중입니다")

        upload_svc = UploadJobService.get_instance()
        if upload_svc.has_active_job():
            raise HTTPException(409, "업로드 작업이 실행 중입니다")

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
            factory = get_session_factory()
            async with factory() as session:
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
                async with factory() as session:
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
                gc.collect()

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

    def _to_response(self, state: PipelineJobState) -> PipelineJobStatusResponse:
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
