"""월간 AI 스케줄러 API 엔드포인트"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from schemas.common import api_response
from schemas.sync import UpdateMonthlyScheduleRequest

from .deps import get_monthly_scheduler_dep

logger = logging.getLogger(__name__)

router = APIRouter(tags=["monthly-scheduler"])


def _build_monthly_status(scheduler) -> dict[str, Any]:
    """월간 스케줄러 상태 딕셔너리 생성 (중복 제거 헬퍼)"""
    info = scheduler.get_schedule_info()
    return {
        "is_running": scheduler.is_running,
        "next_run_time": scheduler.get_next_run_time(),
        "run_day": info["day"],
        "run_hour": info["hour"],
        "run_minute": info["minute"],
    }


@router.get("/status")
async def api_get_monthly_scheduler_status(
    scheduler=Depends(get_monthly_scheduler_dep),
) -> dict[str, Any]:
    """월간 스케줄러 상태 조회"""
    return api_response(_build_monthly_status(scheduler))


@router.post("/start")
async def api_start_monthly_scheduler(
    scheduler=Depends(get_monthly_scheduler_dep),
) -> dict[str, Any]:
    """월간 스케줄러 시작"""
    if not scheduler.is_running:
        await scheduler.start()
    return api_response(_build_monthly_status(scheduler))


@router.post("/stop")
async def api_stop_monthly_scheduler(
    scheduler=Depends(get_monthly_scheduler_dep),
) -> dict[str, Any]:
    """월간 스케줄러 종료"""
    await scheduler.stop()
    status = _build_monthly_status(scheduler)
    status["next_run_time"] = None
    return api_response(status)


@router.post("/schedule")
async def api_update_monthly_schedule(
    request: UpdateMonthlyScheduleRequest,
    scheduler=Depends(get_monthly_scheduler_dep),
) -> dict[str, Any]:
    """월간 스케줄러 실행 시간 변경"""
    success = await scheduler.update_schedule(request.day, request.hour, request.minute)

    if not success:
        raise HTTPException(
            status_code=400,
            detail="일은 1~28, 시간은 0~23시, 분은 0~59 사이여야 합니다",
        )

    return api_response(_build_monthly_status(scheduler))


@router.post("/run")
async def api_run_monthly_job_now(
    scheduler=Depends(get_monthly_scheduler_dep),
) -> dict[str, Any]:
    """월간 AI 작업 즉시 실행 (수동)"""
    try:
        result = await scheduler.run_now()
        return api_response({
            "success": True,
            "message": result.get("message", "월간 AI 작업 완료"),
        })
    except Exception as e:
        logger.error(f"월간 AI 작업 수동 실행 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"월간 AI 작업 실행 실패: {str(e)}",
        )
