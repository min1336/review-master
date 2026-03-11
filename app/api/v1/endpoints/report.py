"""
AI 리포트 조회 API

Router: /api/reports
담당: 리포트 조회, 목록, PDF 다운로드
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
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
# Batch PDF 비동기 작업 (인메모리)
# ================================================================

_batch_pdf_jobs: dict[str, dict[str, Any]] = {}
_BATCH_PDF_MAX_JOBS = 10
_BATCH_PDF_TTL = 600  # 10분


def _cleanup_stale_jobs() -> None:
    """TTL 초과 작업 제거 (메모리 누수 방지)"""
    now = time.monotonic()
    stale = [k for k, v in _batch_pdf_jobs.items()
             if now - v.get("created_at", 0) > _BATCH_PDF_TTL]
    for k in stale:
        _batch_pdf_jobs.pop(k, None)


@router.post("/batch-pdf", status_code=202, response_model=ApiResponseModel[dict])
async def api_batch_download_pdf(
    req: BatchPdfRequest,
) -> dict[str, Any]:
    """일괄 PDF ZIP 생성 — 비동기 작업 제출

    백그라운드에서 ZIP을 생성하여 504 타임아웃 방지.
    GET /batch-pdf/job/{job_id}로 상태 폴링,
    GET /batch-pdf/download/{job_id}로 완성된 ZIP 다운로드.
    """
    validate_date_range_d(req.start_date, req.end_date)

    _cleanup_stale_jobs()

    job_id = uuid.uuid4().hex[:12]
    _batch_pdf_jobs[job_id] = {
        "status": "processing",
        "progress": 0,
        "message": "ZIP 생성 준비 중",
        "zip_bytes": None,
        "pdf_count": 0,
        "skipped": [],
        "error": None,
        "filename": f"AI_Reports_{req.start_date}_{req.end_date}.zip",
        "created_at": time.monotonic(),
    }

    asyncio.create_task(_run_batch_pdf_job(
        job_id, list(req.branch_ids), req.start_date, req.end_date,
    ))

    return api_response({"job_id": job_id, "status": "processing"})


@router.get("/batch-pdf/job/{job_id}", response_model=ApiResponseModel[dict])
async def api_batch_pdf_status(
    job_id: str = Path(..., pattern=r"^[0-9a-f]{12}$"),
) -> dict[str, Any]:
    """일괄 PDF 작업 상태 조회"""
    job = _batch_pdf_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다")
    return api_response({
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"],
        "message": job["message"],
        "pdf_count": job["pdf_count"],
        "skipped": job["skipped"],
        "error": job["error"],
    })


@router.get("/batch-pdf/download/{job_id}")
async def api_batch_pdf_download(
    job_id: str = Path(..., pattern=r"^[0-9a-f]{12}$"),
) -> Response:
    """완성된 ZIP 파일 다운로드"""
    import urllib.parse

    job = _batch_pdf_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다")
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail="아직 완료되지 않았습니다")
    if not job["zip_bytes"]:
        raise HTTPException(status_code=404, detail="ZIP 파일이 없습니다")

    zip_bytes = job["zip_bytes"]
    filename = job.get("filename", "AI_Reports.zip")
    encoded = urllib.parse.quote(filename)

    # 다운로드 후 메모리 정리
    _batch_pdf_jobs.pop(job_id, None)

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


async def _run_batch_pdf_job(
    job_id: str,
    branch_ids: list[int],
    start_date: date,
    end_date: date,
) -> None:
    """백그라운드에서 리포트 조회 → PDF 생성 → ZIP 패킹"""
    import io
    import json as _json
    import zipfile

    job = _batch_pdf_jobs.get(job_id)
    if not job:
        return

    try:
        from infrastructure.pdf.generator import PDFGenerator
        from repository.database import get_session_factory
        from repository.report_repository import ReportRepository
        from schemas.report import ReportData

        parsed_start = date_to_utc(start_date)
        parsed_end = date_to_utc(end_date, end_of_day=True)
        date_label = f"{start_date}_{end_date}"
        skipped: list[int] = []

        # Phase 1: 리포트 데이터 조회
        job["message"] = "리포트 데이터 조회 중"
        branch_reports: list[tuple[int, ReportData]] = []

        factory = get_session_factory()
        async with factory() as session:
            repo = ReportRepository(session)
            for i, branch_id in enumerate(branch_ids):
                try:
                    saved = await repo.get_by_branch_and_period(
                        branch_id, parsed_start, parsed_end,
                    )
                    if not saved:
                        skipped.append(branch_id)
                        continue
                    report_data = saved.get("report_data")
                    if isinstance(report_data, str):
                        report_data = _json.loads(report_data)
                    branch_reports.append((branch_id, ReportData(**report_data)))
                except Exception:
                    logger.exception("Batch PDF: branch %d 조회 실패", branch_id)
                    skipped.append(branch_id)
                job["progress"] = int((i + 1) / len(branch_ids) * 30)

        if not branch_reports:
            job["status"] = "failed"
            job["error"] = "생성된 리포트가 없습니다"
            job["skipped"] = skipped
            return

        # Phase 2: PDF 생성 (병렬, Semaphore(3))
        pdf_gen = PDFGenerator()
        sem = asyncio.Semaphore(1)
        completed_count = 0

        async def _gen_pdf(report: ReportData) -> bytes:
            nonlocal completed_count
            async with sem:
                result = await asyncio.to_thread(pdf_gen.generate_simple, report)
                completed_count += 1
                job["progress"] = 30 + int(completed_count / len(branch_reports) * 60)
                job["message"] = f"PDF 생성 중 ({completed_count}/{len(branch_reports)})"
                return result

        pdf_results = await asyncio.gather(
            *[_gen_pdf(rpt) for _, rpt in branch_reports],
            return_exceptions=True,
        )

        # Phase 3: ZIP 패킹
        job["message"] = "ZIP 파일 생성 중"
        job["progress"] = 90

        buf = io.BytesIO()
        pdf_count = 0
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for (branch_id, report), pdf_result in zip(branch_reports, pdf_results):
                if isinstance(pdf_result, Exception):
                    logger.error("Batch PDF: branch %d PDF 생성 실패: %s", branch_id, pdf_result)
                    skipped.append(branch_id)
                    continue
                safe_name = re.sub(r'[\\/:*?"<>|]', '_', report.branch_name)
                zf.writestr(f"AI_Report_{safe_name}_{date_label}.pdf", pdf_result)
                pdf_count += 1

            if skipped:
                skip_text = f"리포트 미생성 업체 ID: {', '.join(map(str, skipped))}\n"
                skip_text += "해당 업체는 개별 리포트를 먼저 생성해주세요."
                zf.writestr("_skipped.txt", skip_text)

        if pdf_count == 0:
            job["status"] = "failed"
            job["error"] = "PDF 생성에 모두 실패했습니다"
            job["skipped"] = skipped
            return

        job["status"] = "completed"
        job["progress"] = 100
        job["message"] = f"{pdf_count}개 PDF 생성 완료"
        job["pdf_count"] = pdf_count
        job["skipped"] = skipped
        job["zip_bytes"] = buf.getvalue()
        logger.info("Batch PDF 완료: job=%s, pdf_count=%d", job_id, pdf_count)

    except Exception as e:
        logger.exception("Batch PDF job 실패: %s", job_id)
        job["status"] = "failed"
        job["error"] = str(e)
        job["message"] = "ZIP 생성 중 오류 발생"


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
