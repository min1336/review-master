"""
AI 리포트 API

Router: /api/reports
담당: AI 리포트 생성 및 PDF 다운로드
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from dateutil.relativedelta import relativedelta

from core.timezone import utc_now
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import Response
from pydantic import BaseModel
from schemas.common import api_response, parse_date, validate_date_range
from services.report_job_service import ReportJobService
from services.report_service import ReportService

from .deps import get_report_job_service, get_report_service, get_review_repo

logger = logging.getLogger(__name__)

router = APIRouter(tags=["report"])

MINIMUM_REVIEW_THRESHOLD = 30


class ReportRequest(BaseModel):
    """리포트 생성 요청"""
    start_date: str  # YYYY-MM-DD
    end_date: str  # YYYY-MM-DD

# ================================================================
# Path parameter 경로 (/{branch_id}/*)
# ================================================================


@router.get("/{branch_id}/review-count")
async def api_get_review_count(
    branch_id: int,
    start_date: str = Query(..., description="시작일 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="종료일 (YYYY-MM-DD)"),
    review_repo: "BranchReviewRepository" = Depends(get_review_repo),
) -> dict[str, Any]:
    """
    리포트 생성 전 리뷰 수 사전 확인

    선택된 기간과 표준 5개 기간(1m/3m/6m/12m/all)의 리뷰 수를 한번에 반환합니다.
    threshold(30건) 이상인 최단 기간을 recommended_period로 제시합니다.
    """
    parsed_start = parse_date(start_date)
    parsed_end = parse_date(end_date, end_of_day=True)
    validate_date_range(parsed_start, parsed_end)

    try:
        today = utc_now()
        today_date = datetime(today.year, today.month, today.day)
        period_defs = [
            ("1m", 1), ("3m", 3), ("6m", 6), ("12m", 12),
        ]

        # 모든 쿼리를 병렬로 실행 (selected + 4개 기간 + all)
        selected_coro = review_repo.count_by_branch(
            branch_id, review_date_from=parsed_start, review_date_to=parsed_end,
        )
        period_coros = [
            review_repo.count_by_branch(
                branch_id,
                review_date_from=today_date - relativedelta(months=months),
                review_date_to=today,
            )
            for _label, months in period_defs
        ]
        all_coro = review_repo.count_by_branch(branch_id)

        results = await asyncio.gather(selected_coro, *period_coros, all_coro)

        selected_count = results[0]
        period_counts: dict[str, int] = {
            label: results[i + 1] for i, (label, _) in enumerate(period_defs)
        }
        period_counts["all"] = results[-1]

        # 추천 기간: threshold 이상인 최단 기간
        recommended_period = None
        for label, _months in period_defs:
            if period_counts[label] >= MINIMUM_REVIEW_THRESHOLD:
                recommended_period = label
                break
        if recommended_period is None:
            recommended_period = "all"

        return api_response({
            "selected_count": selected_count,
            "period_counts": period_counts,
            "threshold": MINIMUM_REVIEW_THRESHOLD,
            "recommended_period": recommended_period,
        })
    except Exception as e:
        logger.exception("리뷰 수 확인 오류")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{branch_id}")
async def api_get_report(
    branch_id: int,
    start_date: str = Query(..., description="시작일 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="종료일 (YYYY-MM-DD)"),
    service: ReportService = Depends(get_report_service),
) -> dict[str, Any]:
    """저장된 리포트 조회 (없으면 신규 생성)"""
    parsed_start = parse_date(start_date)
    parsed_end = parse_date(end_date, end_of_day=True)
    validate_date_range(parsed_start, parsed_end)

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
        raise HTTPException(status_code=500, detail=str(e)) from e


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
        raise HTTPException(status_code=500, detail=str(e)) from e


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
    start_date = parse_date(data.start_date)
    end_date = parse_date(data.end_date, end_of_day=True)
    validate_date_range(start_date, end_date)

    try:
        job_id = await job_service.submit_job(
            branch_id=branch_id,
            start_date=start_date,
            end_date=end_date,
        )
        return api_response({
            "job_id": job_id,
            "poll_url": f"/api/reports/{branch_id}/job/{job_id}",
        })
    except Exception as e:
        logger.exception("비동기 리포트 생성 요청 실패")
        raise HTTPException(status_code=500, detail=str(e)) from e


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
    start_date = parse_date(data.start_date)
    end_date = parse_date(data.end_date, end_of_day=True)
    validate_date_range(start_date, end_date)

    try:
        report = await service.generate_report(
            branch_id=branch_id,
            start_date=start_date,
            end_date=end_date,
        )
        report_data = report.model_dump()
        report_data["is_new"] = True
        return api_response(report_data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.exception("리포트 생성 오류")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{branch_id}/regenerate")
async def api_regenerate_report(
    branch_id: int,
    data: ReportRequest,
    service: ReportService = Depends(get_report_service),
) -> dict[str, Any]:
    """AI 리포트 재생성 (기존 리포트 덮어쓰기)"""
    start_date = parse_date(data.start_date)
    end_date = parse_date(data.end_date, end_of_day=True)
    validate_date_range(start_date, end_date)

    try:
        report = await service.regenerate_report(
            branch_id=branch_id,
            start_date=start_date,
            end_date=end_date,
        )
        report_data = report.model_dump()
        report_data["is_new"] = True
        return api_response(report_data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.exception("리포트 재생성 오류")
        raise HTTPException(status_code=500, detail=str(e)) from e


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
    start_date: str = Query(..., description="시작일 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="종료일 (YYYY-MM-DD)"),
    service: ReportService = Depends(get_report_service),
) -> dict[str, Any]:
    """AI 리포트 삭제"""
    parsed_start = parse_date(start_date)
    parsed_end = parse_date(end_date, end_of_day=True)
    validate_date_range(parsed_start, parsed_end)

    try:
        deleted = await service.delete_report(
            branch_id=branch_id,
            start_date=parsed_start,
            end_date=parsed_end,
        )
        if deleted:
            return api_response({"message": "리포트가 삭제되었습니다."})
        else:
            raise HTTPException(status_code=404, detail="삭제할 리포트를 찾을 수 없습니다.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("리포트 삭제 오류")
        raise HTTPException(status_code=500, detail=str(e)) from e


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
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{branch_id}/history")
async def api_get_report_history(
    branch_id: int,
    start_date: str = Query(..., description="시작일 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="종료일 (YYYY-MM-DD)"),
    limit: int = Query(default=10, le=50),
    service: ReportService = Depends(get_report_service),
) -> dict[str, Any]:
    """특정 기간의 리포트 버전 히스토리 조회"""
    parsed_start = parse_date(start_date)
    parsed_end = parse_date(end_date, end_of_day=True)
    validate_date_range(parsed_start, parsed_end)

    try:
        history = await service.get_report_history(
            branch_id=branch_id,
            period_start=parsed_start,
            period_end=parsed_end,
            limit=limit,
        )
        return api_response(history)
    except Exception as e:
        logger.exception("리포트 히스토리 조회 오류")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{branch_id}/pdf")
async def api_download_report_pdf(
    branch_id: int,
    start_date: str = Query(..., description="시작일 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="종료일 (YYYY-MM-DD)"),
    service: ReportService = Depends(get_report_service),
) -> Response:
    """AI 리포트 PDF 다운로드"""
    from infrastructure.pdf.generator import PDFGenerator

    parsed_start = parse_date(start_date)
    parsed_end = parse_date(end_date, end_of_day=True)
    validate_date_range(parsed_start, parsed_end)

    try:
        report, _is_new = await service.get_or_generate_report(
            branch_id=branch_id,
            start_date=parsed_start,
            end_date=parsed_end,
        )

        pdf_generator = PDFGenerator()
        pdf_bytes = pdf_generator.generate_simple(report)

        import urllib.parse
        filename = f"AI_Report_{report.branch_name}_{start_date}_{end_date}.pdf"
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
        raise HTTPException(status_code=500, detail=str(e)) from e
