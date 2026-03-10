"""
AI 리포트 조회 API

Router: /api/reports
담당: 리포트 조회, 목록, PDF 다운로드
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import date

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from core.timezone import date_to_utc
from schemas.common import ApiResponseModel, api_response, validate_date_range_d
from schemas.report import BatchPdfRequest
from services.report_service import ReportService

from ._common import resolve_period_or_dates
from .deps import get_report_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["report"])

# ================================================================
# 고정 경로 (Fixed-path routes) — path parameter 라우트보다 위에 배치
# ================================================================


@router.post("/batch-pdf")
async def api_batch_download_pdf(
    req: BatchPdfRequest,
    service: ReportService = Depends(get_report_service),
) -> Response:
    """선택된 업체들의 PDF를 ZIP으로 일괄 다운로드

    캐시된 리포트만 포함하며, 미생성 업체는 skipped 목록으로 반환.
    ZIP 내 각 PDF 파일명: AI_Report_{업체명}_{기간}.pdf
    """
    import io
    import zipfile
    import urllib.parse

    validate_date_range_d(req.start_date, req.end_date)
    parsed_start = date_to_utc(req.start_date)
    parsed_end = date_to_utc(req.end_date, end_of_day=True)
    date_label = f"{req.start_date}_{req.end_date}"

    async def _build_zip() -> tuple[bytes, int]:
        buf = io.BytesIO()
        skipped: list[int] = []

        # Phase 1: 리포트 조회 (순차 — 세션 공유)
        branch_reports: list[tuple[int, Any]] = []
        for branch_id in req.branch_ids:
            try:
                report = await service.get_saved_report(
                    branch_id, parsed_start, parsed_end,
                )
                if report is None:
                    skipped.append(branch_id)
                else:
                    branch_reports.append((branch_id, report))
            except Exception:
                logger.exception("Batch PDF: branch %d 조회 실패", branch_id)
                skipped.append(branch_id)

        # Phase 2: PDF 생성 (병렬 — Semaphore(5))
        sem = asyncio.Semaphore(5)

        async def _gen_pdf(report: Any) -> bytes:
            async with sem:
                return await service.generate_pdf(report)

        pdf_results = await asyncio.gather(
            *[_gen_pdf(rpt) for _, rpt in branch_reports],
            return_exceptions=True,
        )

        pdf_count = 0
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for (branch_id, report), pdf_result in zip(branch_reports, pdf_results):
                if isinstance(pdf_result, Exception):
                    logger.error("Batch PDF: branch %d PDF 생성 실패: %s", branch_id, pdf_result)
                    skipped.append(branch_id)
                    continue
                safe_name = re.sub(r'[\\/:*?"<>|]', '_', report.branch_name)
                filename = f"AI_Report_{safe_name}_{date_label}.pdf"
                zf.writestr(filename, pdf_result)
                pdf_count += 1

            if skipped:
                skip_text = f"리포트 미생성 업체 ID: {', '.join(map(str, skipped))}\n"
                skip_text += "해당 업체는 개별 리포트를 먼저 생성해주세요."
                zf.writestr("_skipped.txt", skip_text)

        return buf.getvalue(), pdf_count

    try:
        zip_bytes, pdf_count = await asyncio.wait_for(_build_zip(), timeout=120)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504, detail="일괄 PDF 생성 시간 초과 (120초). 선택 수를 줄여주세요.",
        )

    if pdf_count == 0:
        raise HTTPException(
            status_code=404,
            detail="선택된 업체의 리포트가 모두 미생성 상태입니다. 개별 리포트를 먼저 생성해주세요.",
        )

    zip_filename = f"AI_Reports_{date_label}.zip"
    encoded_filename = urllib.parse.quote(zip_filename)

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
        },
    )


# ================================================================
# Path parameter 경로 (/{branch_id}/*)
# ================================================================


@router.get("/{branch_id}/review-count", response_model=ApiResponseModel[dict])
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


@router.get("/{branch_id}/list", response_model=ApiResponseModel[list])
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


@router.delete("/{branch_id}", response_model=ApiResponseModel[dict])
async def api_delete_report(
    branch_id: int,
    start_date: date = Query(..., description="시작일 (YYYY-MM-DD)"),
    end_date: date = Query(..., description="종료일 (YYYY-MM-DD)"),
    service: ReportService = Depends(get_report_service),
) -> dict[str, Any]:
    """리포트 삭제"""
    validate_date_range_d(start_date, end_date)

    try:
        deleted = await service.delete_report(
            branch_id,
            date_to_utc(start_date),
            date_to_utc(end_date),
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="삭제할 리포트를 찾을 수 없습니다.")
        return api_response({"deleted": True})
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("리포트 삭제 오류")
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

    period, start_date+end_date 모두 미지정 시 리뷰 수 기반 최적 기간을 자동 선택합니다.
    둘 다 지정하면 period가 우선합니다.
    """
    import urllib.parse

    if not period and not (start_date and end_date):
        period = await service.resolve_recommended_period(branch_id)

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

        safe_name = re.sub(r'[\\/:*?"<>|]', '_', report.branch_name)
        filename = f"AI_Report_{safe_name}_{date_label}.pdf"
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


@router.get("/{branch_id}", response_model=ApiResponseModel[dict])
async def api_get_report(
    branch_id: int,
    period: str | None = Query(None, pattern=r"^(all|1y|12m|6m|3m|1m)$", description="기간 프리셋 (1m/3m/6m/12m/1y/all)"),
    start_date: date | None = Query(None, description="시작일 (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="종료일 (YYYY-MM-DD)"),
    service: ReportService = Depends(get_report_service),
) -> dict[str, Any]:
    """저장된 리포트 조회 (없으면 신규 생성)

    period, start_date+end_date 모두 미지정 시 리뷰 수 기반 최적 기간을 자동 선택합니다.
    둘 다 지정하면 period가 우선합니다.
    """
    auto_detected = False
    if not period and not (start_date and end_date):
        period = await service.resolve_recommended_period(branch_id)
        auto_detected = True

    parsed_start, parsed_end = resolve_period_or_dates(period, start_date, end_date)

    try:
        report, is_new = await service.get_or_generate_report(
            branch_id=branch_id,
            start_date=parsed_start,
            end_date=parsed_end,
        )
        report_data = report.model_dump()
        report_data["is_new"] = is_new
        report_data["resolved_period"] = period
        report_data["auto_detected"] = auto_detected
        return api_response(report_data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.exception("리포트 조회 오류")
        raise HTTPException(status_code=500, detail="서버 오류가 발생했습니다.") from e
