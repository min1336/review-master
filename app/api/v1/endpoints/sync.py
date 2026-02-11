from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from core.config import get_settings
from infrastructure.scheduler.sync_scheduler import get_scheduler
from schemas.sync import (
    MarkReadRequest,
    MarkReadResponse,
    SchedulerStatusResponse,
    SyncJobStatusResponse,
    UpdateScheduleTimeRequest,
)
from .deps import get_sync_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["sync"])

@router.post("/reviews", response_model=SyncJobStatusResponse, status_code=202)
async def sync_reviews() -> JSONResponse:
    from services.sync_job_service import SyncJobService

    service = SyncJobService.get_instance()
    result = await service.submit_job()

    return JSONResponse(
        status_code=202,
        content=result.model_dump(mode="json"),
    )

@router.get("/jobs/{job_id}", response_model=SyncJobStatusResponse)
async def get_sync_job_status(job_id: str) -> SyncJobStatusResponse:
    from services.sync_job_service import SyncJobService

    service = SyncJobService.get_instance()
    result = service.get_job_status(job_id)

    if not result:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다")

    return result

@router.delete("/jobs/{job_id}")
async def cancel_sync_job(job_id: str) -> dict:
    from services.sync_job_service import SyncJobService

    service = SyncJobService.get_instance()
    cancelled = await service.cancel_job(job_id)

    if not cancelled:
        raise HTTPException(status_code=404, detail="취소할 수 있는 작업이 없습니다")

    return {"success": True, "message": "작업이 취소되었습니다"}

@router.post("/reviews/read", response_model=MarkReadResponse)
async def mark_reviews_as_read(
    request: MarkReadRequest,
    sync_service=Depends(get_sync_service),
) -> MarkReadResponse:
    marked_count = await sync_service.mark_reviews_as_read(request.review_ids)

    return MarkReadResponse(
        success=True,
        marked_count=marked_count,
    )

@router.get("/scheduler/status", response_model=SchedulerStatusResponse)
async def get_scheduler_status() -> SchedulerStatusResponse:
    scheduler = get_scheduler()
    hour, minute = scheduler.get_schedule_time()

    return SchedulerStatusResponse(
        is_running=scheduler.is_running,
        next_run_time=scheduler.get_next_run_time(),
        sync_hour=hour,
        sync_minute=minute,
    )

@router.post("/scheduler/time", response_model=SchedulerStatusResponse)
async def update_scheduler_time(
    request: UpdateScheduleTimeRequest,
) -> SchedulerStatusResponse:
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