"""리뷰 동기화 API 엔드포인트"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from core.config import get_settings
from infrastructure.scheduler.sync_scheduler import get_scheduler
from schemas.sync import (
    MarkReadRequest,
    MarkReadResponse,
    SchedulerStatusResponse,
    SyncResultResponse,
    SyncStatusResponse,
    UpdateIntervalRequest,
)

from .deps import get_sync_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/status", response_model=SyncStatusResponse)
async def get_sync_status(
    sync_service=Depends(get_sync_service),
) -> SyncStatusResponse:
    """
    동기화 상태 조회

    - 마지막 동기화 시간
    - 전체 리뷰 수
    - 신규 리뷰 수
    """
    return await sync_service.get_athena_sync_status()


@router.post("/reviews", response_model=SyncResultResponse)
async def sync_reviews(
    sync_service=Depends(get_sync_service),
) -> SyncResultResponse:
    """
    Athena에서 신규 리뷰 동기화

    1. 마지막 동기화 시간 이후의 리뷰를 Athena에서 조회
    2. branch_reviews 테이블에 저장 (is_new=true)
    3. 동기화 시간 업데이트
    """
    return await sync_service.sync_reviews()


@router.post("/reviews/read", response_model=MarkReadResponse)
async def mark_reviews_as_read(
    request: MarkReadRequest,
    sync_service=Depends(get_sync_service),
) -> MarkReadResponse:
    """
    리뷰 읽음 처리

    - review_ids가 있으면 해당 리뷰만 읽음 처리
    - review_ids가 없으면 모든 신규 리뷰 읽음 처리
    """
    marked_count = await sync_service.mark_reviews_as_read(request.review_ids)

    return MarkReadResponse(
        success=True,
        marked_count=marked_count,
    )


# ============================================================
# 스케줄러 API
# ============================================================
@router.get("/scheduler/status", response_model=SchedulerStatusResponse)
async def get_scheduler_status() -> SchedulerStatusResponse:
    """
    스케줄러 상태 조회

    - 실행 중 여부
    - 다음 실행 시간
    - 동기화 간격 (현재/최소/최대)
    """
    scheduler = get_scheduler()

    return SchedulerStatusResponse(
        is_running=scheduler.is_running,
        next_run_time=scheduler.get_next_run_time(),
        interval_minutes=scheduler.get_interval(),
        min_interval=scheduler.MIN_INTERVAL,
        max_interval=scheduler.MAX_INTERVAL,
    )


@router.post("/scheduler/start", response_model=SchedulerStatusResponse)
async def start_scheduler() -> SchedulerStatusResponse:
    """스케줄러 시작"""
    scheduler = get_scheduler()

    if scheduler.is_running:
        return SchedulerStatusResponse(
            is_running=True,
            next_run_time=scheduler.get_next_run_time(),
            interval_minutes=scheduler.get_interval(),
            min_interval=scheduler.MIN_INTERVAL,
            max_interval=scheduler.MAX_INTERVAL,
        )

    await scheduler.start()

    return SchedulerStatusResponse(
        is_running=scheduler.is_running,
        next_run_time=scheduler.get_next_run_time(),
        interval_minutes=scheduler.get_interval(),
        min_interval=scheduler.MIN_INTERVAL,
        max_interval=scheduler.MAX_INTERVAL,
    )


@router.post("/scheduler/stop", response_model=SchedulerStatusResponse)
async def stop_scheduler() -> SchedulerStatusResponse:
    """스케줄러 종료"""
    scheduler = get_scheduler()

    await scheduler.stop()

    return SchedulerStatusResponse(
        is_running=scheduler.is_running,
        next_run_time=None,
        interval_minutes=scheduler.get_interval(),
        min_interval=scheduler.MIN_INTERVAL,
        max_interval=scheduler.MAX_INTERVAL,
    )


@router.post("/scheduler/interval", response_model=SchedulerStatusResponse)
async def update_scheduler_interval(
    request: UpdateIntervalRequest,
) -> SchedulerStatusResponse:
    """
    스케줄러 간격 변경

    - interval_minutes: 5~30분 사이 값
    """
    scheduler = get_scheduler()

    success = await scheduler.update_interval(request.interval_minutes)

    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"간격은 {scheduler.MIN_INTERVAL}~{scheduler.MAX_INTERVAL}분 사이여야 합니다",
        )

    return SchedulerStatusResponse(
        is_running=scheduler.is_running,
        next_run_time=scheduler.get_next_run_time(),
        interval_minutes=scheduler.get_interval(),
        min_interval=scheduler.MIN_INTERVAL,
        max_interval=scheduler.MAX_INTERVAL,
    )
