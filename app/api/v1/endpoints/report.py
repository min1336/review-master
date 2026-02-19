"""
AI 리포트 API

Router: /api/reports
담당: AI 리포트 생성 및 PDF 다운로드
"""

from __future__ import annotations

import logging
from datetime import date

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import Response
from core.timezone import date_to_utc
from schemas.common import api_response, validate_date_range_d
from schemas.report import ReportRequest
from services.report_job_service import ReportJobService
from services.report_service import ReportService

from .deps import get_report_job_service, get_report_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["report"])

# ================================================================
# Path parameter 경로 (/{branch_id}/*)
# ================================================================


@router.get("/{branch_id}/review-count")
async def api_get_review_count(
    branch_id: int,
    start_date: date = Query(..., description="시작일 (YYYY-MM-DD)"),
    end_date: date = Query(..., description="종료일 (YYYY-MM-DD)"),
    service: ReportService = Depends(get_report_service),
) -> dict[str, Any]:
    """
    리포트 생성 전 리뷰 수 사전 확인

    선택된 기간과 표준 5개 기간(1m/3m/6m/12m/all)의 리뷰 수를 한번에 반환합니다.
    threshold(30건) 이상인 최단 기간을 recommended_period로 제시합니다.
    """
    validate_date_range_d(start_date, end_date)

    try:
        result = await service.get_review_count_summary(
            branch_id,
            date_to_utc(start_date),
            date_to_utc(end_date, end_of_day=True),
        )
        return api_response(result)
    except Exception as e:
        logger.exception("리뷰 수 확인 오류")
        raise HTTPException(status_code=500, detail="서버 오류가 발생했습니다.") from e


@router.get("/{branch_id}")
async def api_get_report(
    branch_id: int,
    period: str | None = Query(None, pattern=r"^(all|1y|12m|6m|3m|1m)$", description="기간 프리셋 (1m/3m/6m/12m/1y/all)"),
    start_date: date | None = Query(None, description="시작일 (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="종료일 (YYYY-MM-DD)"),
    service: ReportService = Depends(get_report_service),
) -> dict[str, Any]:
    """저장된 리포트 조회 (없으면 신규 생성)

    period 또는 start_date+end_date 중 하나를 반드시 지정해야 합니다.
    둘 다 지정하면 period가 우선합니다.
    """
    from schemas.common import resolve_period

    if period:
        parsed_start, parsed_end = resolve_period(period)
    elif start_date and end_date:
        validate_date_range_d(start_date, end_date)
        parsed_start = date_to_utc(start_date)
        parsed_end = date_to_utc(end_date, end_of_day=True)
    else:
        raise HTTPException(
            status_code=400,
            detail="period 또는 start_date+end_date를 지정해야 합니다.",
        )

    try:
        report, is_new = await service.get_or_generate_report(
            branch_id=branch_id,
            start_date=parsed_start,
            end_date=parsed_end,
        )
        report_data = report.model_dump()
        report_data["is_new"] = is_new
        return api_response(report_data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.exception("리포트 조회 오류")
        raise HTTPException(status_code=500, detail="서버 오류가 발생했습니다.") from e


@router.get("/{branch_id}/list")
async def api_get_report_list(
    branch_id: int,
    limit: int = Query(default=10, le=50),
    service: ReportService = Depends(get_report_service),
) -> dict[str, Any]:
    """지점의 리포트 목록 조회"""
    try:
        reports = await service.get_report_list(branch_id, limit)
        return api_response(reports)
    except Exception as e:
        logger.exception("리포트 목록 조회 오류")
        raise HTTPException(status_code=500, detail="서버 오류가 발생했습니다.") from e


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
        job_id = await job_service.submit_job(
            branch_id=branch_id,
            start_date=date_to_utc(data.start_date),
            end_date=date_to_utc(data.end_date, end_of_day=True),
        )
        return api_response({
            "job_id": job_id,
            "poll_url": f"/api/reports/{branch_id}/job/{job_id}",
        })
    except Exception as e:
        logger.exception("비동기 리포트 생성 요청 실패")
        raise HTTPException(status_code=500, detail="서버 오류가 발생했습니다.") from e


@router.post("/{branch_id}/generate", status_code=201)
async def api_generate_report(
    branch_id: int,
    data: ReportRequest,
    service: ReportService = Depends(get_report_service),
) -> dict[str, Any]:
    """
    AI 리포트 신규 생성 (저장됨) - 동기 방식

    주의: 긴 처리 시간으로 502 타임아웃 가능. /generate/async 권장.
    """
    validate_date_range_d(data.start_date, data.end_date)

    try:
        report = await service.generate_report(
            branch_id=branch_id,
            start_date=date_to_utc(data.start_date),
            end_date=date_to_utc(data.end_date, end_of_day=True),
        )
        report_data = report.model_dump()
        report_data["is_new"] = True
        return api_response(report_data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.exception("리포트 생성 오류")
        raise HTTPException(status_code=500, detail="서버 오류가 발생했습니다.") from e


@router.post("/{branch_id}/regenerate")
async def api_regenerate_report(
    branch_id: int,
    data: ReportRequest,
    service: ReportService = Depends(get_report_service),
) -> dict[str, Any]:
    """AI 리포트 재생성 (기존 리포트 덮어쓰기)"""
    validate_date_range_d(data.start_date, data.end_date)

    try:
        report = await service.regenerate_report(
            branch_id=branch_id,
            start_date=date_to_utc(data.start_date),
            end_date=date_to_utc(data.end_date, end_of_day=True),
        )
        report_data = report.model_dump()
        report_data["is_new"] = True
        return api_response(report_data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.exception("리포트 재생성 오류")
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


@router.delete("/{branch_id}")
async def api_delete_report(
    branch_id: int,
    start_date: date = Query(..., description="시작일 (YYYY-MM-DD)"),
    end_date: date = Query(..., description="종료일 (YYYY-MM-DD)"),
    service: ReportService = Depends(get_report_service),
) -> dict[str, Any]:
    """AI 리포트 삭제"""
    validate_date_range_d(start_date, end_date)

    try:
        deleted = await service.delete_report(
            branch_id=branch_id,
            start_date=date_to_utc(start_date),
            end_date=date_to_utc(end_date, end_of_day=True),
        )
        if deleted:
            return api_response({"message": "리포트가 삭제되었습니다."})
        else:
            raise HTTPException(status_code=404, detail="삭제할 리포트를 찾을 수 없습니다.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("리포트 삭제 오류")
        raise HTTPException(status_code=500, detail="서버 오류가 발생했습니다.") from e


@router.post("/{branch_id}/viewed/{report_id}")
async def api_mark_report_viewed(
    branch_id: int,
    report_id: int,
    service: ReportService = Depends(get_report_service),
) -> dict[str, Any]:
    """리포트 조회 표시 (NEW 뱃지 제거)"""
    try:
        success = await service.mark_as_viewed(report_id)
        return api_response({"viewed": success})
    except Exception as e:
        logger.exception("리포트 조회 표시 오류")
        raise HTTPException(status_code=500, detail="서버 오류가 발생했습니다.") from e


@router.get("/{branch_id}/history")
async def api_get_report_history(
    branch_id: int,
    start_date: date = Query(..., description="시작일 (YYYY-MM-DD)"),
    end_date: date = Query(..., description="종료일 (YYYY-MM-DD)"),
    limit: int = Query(default=10, le=50),
    service: ReportService = Depends(get_report_service),
) -> dict[str, Any]:
    """특정 기간의 리포트 버전 히스토리 조회"""
    validate_date_range_d(start_date, end_date)

    try:
        history = await service.get_report_history(
            branch_id=branch_id,
            period_start=date_to_utc(start_date),
            period_end=date_to_utc(end_date, end_of_day=True),
            limit=limit,
        )
        return api_response(history)
    except Exception as e:
        logger.exception("리포트 히스토리 조회 오류")
        raise HTTPException(status_code=500, detail="서버 오류가 발생했습니다.") from e


@router.get("/{branch_id}/pdf")
async def api_download_report_pdf(
    branch_id: int,
    period: str | None = Query(None, pattern=r"^(all|1y|12m|6m|3m|1m)$", description="기간 프리셋 (1m/3m/6m/12m/1y/all)"),
    start_date: date | None = Query(None, description="시작일 (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="종료일 (YYYY-MM-DD)"),
    service: ReportService = Depends(get_report_service),
) -> Response:
    """AI 리포트 PDF 다운로드

    period 또는 start_date+end_date 중 하나를 반드시 지정해야 합니다.
    둘 다 지정하면 period가 우선합니다.
    """
    import urllib.parse

    from schemas.common import resolve_period

    if period:
        parsed_start, parsed_end = resolve_period(period)
        date_label = period
    elif start_date and end_date:
        validate_date_range_d(start_date, end_date)
        parsed_start = date_to_utc(start_date)
        parsed_end = date_to_utc(end_date, end_of_day=True)
        date_label = f"{start_date}_{end_date}"
    else:
        raise HTTPException(
            status_code=422,
            detail="period 또는 start_date+end_date를 지정해야 합니다.",
        )

    try:
        report, _is_new = await service.get_or_generate_report(
            branch_id=branch_id,
            start_date=parsed_start,
            end_date=parsed_end,
        )

        pdf_bytes = await service.generate_pdf(report)

        filename = f"AI_Report_{report.branch_name}_{date_label}.pdf"
        encoded_filename = urllib.parse.quote(filename)

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f"attachment; filename*=UTF-8''{encoded_filename}"
                ),
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.exception("PDF 생성 오류")
        raise HTTPException(status_code=500, detail="서버 오류가 발생했습니다.") from e
