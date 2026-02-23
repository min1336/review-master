"""
AI 리포트 비동기 생성 API

Router: /api/reports (report_generate)
담당: 비동기 리포트 생성, 작업 상태 폴링, 작업 취소
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path
from core.timezone import date_to_utc
from schemas.common import api_response, validate_date_range_d
from schemas.report import ReportRequest
from services.report_job_service import ReportJobService

from .deps import get_report_job_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["report"])


@router.post("/{branch_id}/generate/async", status_code=202)
async def api_generate_report_async(
    branch_id: int,
    data: ReportRequest,
    job_service: ReportJobService = Depends(get_report_job_service),
) -> dict[str, Any]:
    """
    비동기 AI 리포트 생성 요청

    502 타임아웃 방지를 위한 백그라운드 작업 방식.
    즉시 job_id를 반환하고, 클라이언트는 /job/{job_id}로 상태를 폴링합니다.
    """
    validate_date_range_d(data.start_date, data.end_date)

    try:
        report_config = data.to_resolved_config()
        job_id = await job_service.submit_job(
            branch_id=branch_id,
            start_date=date_to_utc(data.start_date),
            end_date=date_to_utc(data.end_date, end_of_day=True),
            report_config=report_config,
        )
        return api_response({
            "job_id": job_id,
            "poll_url": f"/api/reports/{branch_id}/job/{job_id}",
        })
    except Exception as e:
        logger.exception("비동기 리포트 생성 요청 실패")
        raise HTTPException(status_code=500, detail="서버 오류가 발생했습니다.") from e


@router.get("/{branch_id}/job/{job_id}")
async def api_get_job_status(
    branch_id: int,
    job_id: UUID = Path(..., description="작업 UUID"),
    job_service: ReportJobService = Depends(get_report_job_service),
) -> dict[str, Any]:
    """비동기 작업 상태 조회 (폴링용)"""
    job_status = await job_service.get_job_status(str(job_id), branch_id=branch_id)

    if not job_status:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    return api_response(job_status)


@router.delete("/{branch_id}/job/{job_id}")
async def api_cancel_job(
    branch_id: int,
    job_id: UUID = Path(..., description="작업 UUID"),
    job_service: ReportJobService = Depends(get_report_job_service),
) -> dict[str, Any]:
    """진행 중인 작업 취소"""
    cancelled = await job_service.cancel_job(str(job_id), branch_id=branch_id)
    return api_response({
        "cancelled": cancelled,
        "message": "작업이 취소되었습니다." if cancelled else "취소할 수 없는 작업입니다.",
    })
