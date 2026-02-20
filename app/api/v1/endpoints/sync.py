from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from schemas.common import api_response
from schemas.sync import (
    MarkReadRequest,
    UpdateScheduleTimeRequest,
)

from .deps import get_sync_job_service, get_sync_scheduler_dep, get_sync_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["sync"])


@router.post("/reviews", status_code=202)
async def api_sync_reviews(
    service=Depends(get_sync_job_service),
) -> dict[str, Any]:
    """비동기 리뷰 동기화 작업 제출"""
    result = await service.submit_job()
    return api_response(result.model_dump(mode="json"))


@router.get("/jobs/{job_id}")
async def api_get_sync_job_status(
    job_id: str,
    service=Depends(get_sync_job_service),
) -> dict[str, Any]:
    """동기화 작업 상태 조회"""
    result = service.get_job_status(job_id)

    if not result:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다")

    return api_response(result.model_dump(mode="json"))


@router.delete("/jobs/{job_id}")
async def api_cancel_sync_job(
    job_id: str,
    service=Depends(get_sync_job_service),
) -> dict[str, Any]:
    """동기화 작업 취소"""
    cancelled = await service.cancel_job(job_id)

    if not cancelled:
        raise HTTPException(status_code=404, detail="취소할 수 있는 작업이 없습니다")

    return api_response({"message": "작업이 취소되었습니다"})


@router.post("/reviews/read")
async def api_mark_reviews_as_read(
    request: MarkReadRequest,
    sync_service=Depends(get_sync_service),
) -> dict[str, Any]:
    """리뷰 읽음 처리"""
    marked_count = await sync_service.mark_reviews_as_read(request.review_ids)
    return api_response({
        "marked_count": marked_count,
    })


@router.get("/scheduler/status")
async def api_get_scheduler_status(
    scheduler=Depends(get_sync_scheduler_dep),
) -> dict[str, Any]:
    """일일 동기화 스케줄러 상태 조회"""
    hour, minute = scheduler.get_schedule_time()
    next_run = scheduler.get_next_run_time()
    return api_response({
        "is_running": scheduler.is_running,
        "next_run_time": next_run.isoformat() if next_run is not None else None,
        "sync_hour": hour,
        "sync_minute": minute,
    })


@router.post("/scheduler/time")
async def api_update_scheduler_time(
    request: UpdateScheduleTimeRequest,
    scheduler=Depends(get_sync_scheduler_dep),
) -> dict[str, Any]:
    """일일 동기화 스케줄러 시간 변경"""
    success = await scheduler.update_schedule_time(request.hour, request.minute)

    if not success:
        raise HTTPException(
            status_code=400,
            detail="시간은 0~23시, 분은 0~59 사이여야 합니다",
        )

    hour, minute = scheduler.get_schedule_time()
    next_run = scheduler.get_next_run_time()
    return api_response({
        "is_running": scheduler.is_running,
        "next_run_time": next_run.isoformat() if next_run is not None else None,
        "sync_hour": hour,
        "sync_minute": minute,
    })
