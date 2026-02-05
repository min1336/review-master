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
    UpdateScheduleTimeRequest,
)

from .deps import get_sync_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sync"])


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
    - 동기화 예정 시간 (시:분)
    """
    scheduler = get_scheduler()
    hour, minute = scheduler.get_schedule_time()

    return SchedulerStatusResponse(
        is_running=scheduler.is_running,
        next_run_time=scheduler.get_next_run_time(),
        sync_hour=hour,
        sync_minute=minute,
    )


@router.post("/scheduler/start", response_model=SchedulerStatusResponse)
async def start_scheduler() -> SchedulerStatusResponse:
    """스케줄러 시작"""
    scheduler = get_scheduler()
    hour, minute = scheduler.get_schedule_time()

    if scheduler.is_running:
        return SchedulerStatusResponse(
            is_running=True,
            next_run_time=scheduler.get_next_run_time(),
            sync_hour=hour,
            sync_minute=minute,
        )

    await scheduler.start()

    return SchedulerStatusResponse(
        is_running=scheduler.is_running,
        next_run_time=scheduler.get_next_run_time(),
        sync_hour=hour,
        sync_minute=minute,
    )


@router.post("/scheduler/stop", response_model=SchedulerStatusResponse)
async def stop_scheduler() -> SchedulerStatusResponse:
    """스케줄러 종료"""
    scheduler = get_scheduler()
    hour, minute = scheduler.get_schedule_time()

    await scheduler.stop()

    return SchedulerStatusResponse(
        is_running=scheduler.is_running,
        next_run_time=None,
        sync_hour=hour,
        sync_minute=minute,
    )


@router.post("/scheduler/time", response_model=SchedulerStatusResponse)
async def update_scheduler_time(
    request: UpdateScheduleTimeRequest,
) -> SchedulerStatusResponse:
    """
    스케줄러 실행 시간 변경

    - hour: 0~23시
    - minute: 0~59분 (기본값 0)
    """
    scheduler = get_scheduler()

    success = await scheduler.update_schedule_time(request.hour, request.minute)

    if not success:
        raise HTTPException(
            status_code=400,
            detail="시간은 0~23시, 분은 0~59 사이여야 합니다",
        )

    hour, minute = scheduler.get_schedule_time()

    return SchedulerStatusResponse(
        is_running=scheduler.is_running,
        next_run_time=scheduler.get_next_run_time(),
        sync_hour=hour,
        sync_minute=minute,
    )
