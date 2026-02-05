"""월간 AI 스케줄러 API 엔드포인트"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from infrastructure.scheduler.monthly_scheduler import get_monthly_scheduler
from schemas.sync import (
    MonthlyJobResultResponse,
    MonthlySchedulerStatusResponse,
    UpdateMonthlyScheduleRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["monthly-scheduler"])


@router.get("/status", response_model=MonthlySchedulerStatusResponse)
async def get_monthly_scheduler_status() -> MonthlySchedulerStatusResponse:
    """
    월간 스케줄러 상태 조회

    - 실행 중 여부
    - 다음 실행 시간
    - 실행 예정 일/시/분
    """
    scheduler = get_monthly_scheduler()
    schedule_info = scheduler.get_schedule_info()

    return MonthlySchedulerStatusResponse(
        is_running=scheduler.is_running,
        next_run_time=scheduler.get_next_run_time(),
        run_day=schedule_info["day"],
        run_hour=schedule_info["hour"],
        run_minute=schedule_info["minute"],
    )


@router.post("/start", response_model=MonthlySchedulerStatusResponse)
async def start_monthly_scheduler() -> MonthlySchedulerStatusResponse:
    """월간 스케줄러 시작"""
    scheduler = get_monthly_scheduler()
    schedule_info = scheduler.get_schedule_info()

    if scheduler.is_running:
        return MonthlySchedulerStatusResponse(
            is_running=True,
            next_run_time=scheduler.get_next_run_time(),
            run_day=schedule_info["day"],
            run_hour=schedule_info["hour"],
            run_minute=schedule_info["minute"],
        )

    await scheduler.start()

    return MonthlySchedulerStatusResponse(
        is_running=scheduler.is_running,
        next_run_time=scheduler.get_next_run_time(),
        run_day=schedule_info["day"],
        run_hour=schedule_info["hour"],
        run_minute=schedule_info["minute"],
    )


@router.post("/stop", response_model=MonthlySchedulerStatusResponse)
async def stop_monthly_scheduler() -> MonthlySchedulerStatusResponse:
    """월간 스케줄러 종료"""
    scheduler = get_monthly_scheduler()
    schedule_info = scheduler.get_schedule_info()

    await scheduler.stop()

    return MonthlySchedulerStatusResponse(
        is_running=scheduler.is_running,
        next_run_time=None,
        run_day=schedule_info["day"],
        run_hour=schedule_info["hour"],
        run_minute=schedule_info["minute"],
    )


@router.post("/schedule", response_model=MonthlySchedulerStatusResponse)
async def update_monthly_schedule(
    request: UpdateMonthlyScheduleRequest,
) -> MonthlySchedulerStatusResponse:
    """
    월간 스케줄러 실행 시간 변경

    - day: 1~28일 (29~31일은 일부 월에 없으므로 제외)
    - hour: 0~23시
    - minute: 0~59분
    """
    scheduler = get_monthly_scheduler()

    success = await scheduler.update_schedule(request.day, request.hour, request.minute)

    if not success:
        raise HTTPException(
            status_code=400,
            detail="일은 1~28, 시간은 0~23시, 분은 0~59 사이여야 합니다",
        )

    schedule_info = scheduler.get_schedule_info()

    return MonthlySchedulerStatusResponse(
        is_running=scheduler.is_running,
        next_run_time=scheduler.get_next_run_time(),
        run_day=schedule_info["day"],
        run_hour=schedule_info["hour"],
        run_minute=schedule_info["minute"],
    )


@router.post("/run", response_model=MonthlyJobResultResponse)
async def run_monthly_job_now() -> MonthlyJobResultResponse:
    """
    월간 AI 작업 즉시 실행 (수동)

    - 지난 달 기간의 리포트 생성
    - 리뷰 10개 이상인 지점 대상
    """
    scheduler = get_monthly_scheduler()

    try:
        result = await scheduler.run_now()
        return MonthlyJobResultResponse(
            success=True,
            message=result.get("message", "월간 AI 작업 완료"),
        )
    except Exception as e:
        logger.error(f"월간 AI 작업 수동 실행 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"월간 AI 작업 실행 실패: {str(e)}",
        )
