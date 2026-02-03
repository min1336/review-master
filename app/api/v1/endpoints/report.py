"""
AI 리포트 API

Router: /api/report
담당: AI 리포트 생성 및 PDF 다운로드
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import Response
from pydantic import BaseModel
from services.report_job_service import ReportJobService
from services.report_service import ReportService

from .deps import get_report_job_service, get_report_service

router = APIRouter(tags=["report"])


class ReportRequest(BaseModel):
    """리포트 생성 요청"""
    start_date: str  # YYYY-MM-DD
    end_date: str  # YYYY-MM-DD


def parse_date(date_str: str, end_of_day: bool = False) -> datetime:
    """날짜 문자열을 datetime으로 파싱"""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        if end_of_day:
            dt = dt.replace(hour=23, minute=59, second=59)
        return dt
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format: '{date_str}'. Expected YYYY-MM-DD format.",
        ) from e


@router.get("/{branch_id}")
async def api_get_report(
    branch_id: int,
    start_date: str = Query(..., description="시작일 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="종료일 (YYYY-MM-DD)"),
    service: ReportService = Depends(get_report_service),
) -> dict[str, Any]:
    """
    저장된 리포트 조회 (없으면 신규 생성)

    Args:
        branch_id: 지점 ID
        start_date: 시작일
        end_date: 종료일

    Returns:
        리포트 데이터 (JSON) + 신규 생성 여부
    """
    parsed_start = parse_date(start_date)
    parsed_end = parse_date(end_date, end_of_day=True)

    if parsed_start > parsed_end:
        raise HTTPException(
            status_code=400,
            detail="시작일이 종료일보다 늦을 수 없습니다.",
        )

    try:
        report, is_new = await service.get_or_generate_report(
            branch_id=branch_id,
            start_date=parsed_start,
            end_date=parsed_end,
        )
        return {
            "success": True,
            "data": report.model_dump(),
            "is_new": is_new,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        import logging
        logging.exception("리포트 조회 오류")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{branch_id}/list")
async def api_get_report_list(
    branch_id: int,
    limit: int = Query(default=10, le=50),
    service: ReportService = Depends(get_report_service),
) -> dict[str, Any]:
    """
    지점의 리포트 목록 조회

    Args:
        branch_id: 지점 ID
        limit: 조회 개수 (최대 50)

    Returns:
        리포트 목록 (메타데이터만)
    """
    try:
        reports = await service.get_report_list(branch_id, limit)
        return {"success": True, "data": reports}
    except Exception as e:
        import logging
        logging.exception("리포트 목록 조회 오류")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{branch_id}/generate/async")
async def api_generate_report_async(
    branch_id: int,
    data: ReportRequest,
    job_service: ReportJobService = Depends(get_report_job_service),
) -> dict[str, Any]:
    """
    비동기 AI 리포트 생성 요청

    502 타임아웃 방지를 위한 백그라운드 작업 방식.
    즉시 job_id를 반환하고, 클라이언트는 /job/{job_id}로 상태를 폴링합니다.

    Args:
        branch_id: 지점 ID
        data: 기간 설정 (start_date, end_date)

    Returns:
        job_id: 작업 ID (폴링용)
        poll_url: 상태 조회 URL
    """
    start_date = parse_date(data.start_date)
    end_date = parse_date(data.end_date, end_of_day=True)

    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="시작일이 종료일보다 늦을 수 없습니다.",
        )

    try:
        job_id = await job_service.submit_job(
            branch_id=branch_id,
            start_date=start_date,
            end_date=end_date,
        )
        return {
            "success": True,
            "job_id": job_id,
            "poll_url": f"/api/v2/report/{branch_id}/job/{job_id}",
        }
    except Exception as e:
        import logging

        logging.exception("비동기 리포트 생성 요청 실패")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{branch_id}/generate")
async def api_generate_report(
    branch_id: int,
    data: ReportRequest,
    service: ReportService = Depends(get_report_service),
) -> dict[str, Any]:
    """
    AI 리포트 신규 생성 (저장됨) - 동기 방식

    주의: 긴 처리 시간으로 502 타임아웃 가능. /generate/async 권장.

    Args:
        branch_id: 지점 ID
        data: 기간 설정 (start_date, end_date)

    Returns:
        리포트 데이터 (JSON)
    """
    start_date = parse_date(data.start_date)
    end_date = parse_date(data.end_date, end_of_day=True)

    # 날짜 유효성 검사
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="시작일이 종료일보다 늦을 수 없습니다.",
        )

    try:
        report = await service.generate_report(
            branch_id=branch_id,
            start_date=start_date,
            end_date=end_date,
        )
        return {"success": True, "data": report.model_dump(), "is_new": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        import logging
        logging.exception("리포트 생성 오류")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{branch_id}/regenerate")
async def api_regenerate_report(
    branch_id: int,
    data: ReportRequest,
    service: ReportService = Depends(get_report_service),
) -> dict[str, Any]:
    """
    AI 리포트 재생성 (기존 리포트 덮어쓰기)

    Args:
        branch_id: 지점 ID
        data: 기간 설정 (start_date, end_date)

    Returns:
        리포트 데이터 (JSON)
    """
    start_date = parse_date(data.start_date)
    end_date = parse_date(data.end_date, end_of_day=True)

    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="시작일이 종료일보다 늦을 수 없습니다.",
        )

    try:
        report = await service.regenerate_report(
            branch_id=branch_id,
            start_date=start_date,
            end_date=end_date,
        )
        return {"success": True, "data": report.model_dump(), "is_new": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        import logging
        logging.exception("리포트 재생성 오류")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{branch_id}/job/{job_id}")
async def api_get_job_status(
    branch_id: int,
    job_id: UUID = Path(..., description="작업 UUID"),
    job_service: ReportJobService = Depends(get_report_job_service),
) -> dict[str, Any]:
    """
    비동기 작업 상태 조회 (폴링용)

    클라이언트는 2초 간격으로 이 엔드포인트를 호출하여 진행 상황을 확인합니다.

    Args:
        branch_id: 지점 ID
        job_id: 작업 UUID

    Returns:
        status: pending/processing/completed/failed
        progress: 0-100 (진행률)
        error_message: 에러 메시지 (실패 시)
        report_id: 생성된 리포트 ID (완료 시)
    """
    # branch_id 소유권 검증 포함
    job_status = await job_service.get_job_status(str(job_id), branch_id=branch_id)

    if not job_status:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    return {"success": True, "data": job_status}


@router.delete("/{branch_id}/job/{job_id}")
async def api_cancel_job(
    branch_id: int,
    job_id: UUID = Path(..., description="작업 UUID"),
    job_service: ReportJobService = Depends(get_report_job_service),
) -> dict[str, Any]:
    """
    진행 중인 작업 취소

    Args:
        branch_id: 지점 ID
        job_id: 작업 UUID

    Returns:
        취소 성공 여부
    """
    # branch_id 소유권 검증 포함
    cancelled = await job_service.cancel_job(str(job_id), branch_id=branch_id)
    return {"success": cancelled, "message": "작업이 취소되었습니다." if cancelled else "취소할 수 없는 작업입니다."}


@router.get("/{branch_id}/pdf")
async def api_download_report_pdf(
    branch_id: int,
    start_date: str = Query(..., description="시작일 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="종료일 (YYYY-MM-DD)"),
    service: ReportService = Depends(get_report_service),
) -> Response:
    """
    AI 리포트 PDF 다운로드

    Args:
        branch_id: 지점 ID
        start_date: 시작일
        end_date: 종료일

    Returns:
        PDF 파일 응답
    """
    from infrastructure.pdf.generator import PDFGenerator

    parsed_start = parse_date(start_date)
    parsed_end = parse_date(end_date, end_of_day=True)

    # 날짜 유효성 검사
    if parsed_start > parsed_end:
        raise HTTPException(
            status_code=400,
            detail="시작일이 종료일보다 늦을 수 없습니다.",
        )

    try:
        # 리포트 데이터 생성
        report = await service.generate_report(
            branch_id=branch_id,
            start_date=parsed_start,
            end_date=parsed_end,
        )

        # PDF 생성 (단순 텍스트 버전 - Docker 경량화)
        pdf_generator = PDFGenerator()
        pdf_bytes = pdf_generator.generate_simple(report)

        # 파일명 생성 (한글 인코딩 처리)
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
        import logging
        logging.exception("PDF 생성 오류")
        raise HTTPException(status_code=500, detail=str(e)) from e
