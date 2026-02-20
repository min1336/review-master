"""
AI 리포트 조회 API

Router: /api/reports
담당: 리포트 조회, 목록, PDF 다운로드
"""

from __future__ import annotations

import logging
from datetime import date

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from core.timezone import date_to_utc
from schemas.common import api_response, validate_date_range_d
from services.report_service import ReportService

from ._common import resolve_period_or_dates
from .deps import get_report_service

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
    parsed_start, parsed_end = resolve_period_or_dates(period, start_date, end_date)

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

    parsed_start, parsed_end = resolve_period_or_dates(
        period, start_date, end_date, error_status=422,
    )
    date_label = period if period else f"{start_date}_{end_date}"

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
