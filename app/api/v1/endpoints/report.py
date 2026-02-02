"""
AI 리포트 API

Router: /api/report
담당: AI 리포트 생성 및 PDF 다운로드
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from services.report_service import ReportService

from .deps import get_report_service

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


@router.post("/{branch_id}/generate")
async def api_generate_report(
    branch_id: int,
    data: ReportRequest,
    service: ReportService = Depends(get_report_service),
) -> dict[str, Any]:
    """
    AI 리포트 신규 생성 (저장됨)

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

        # PDF 생성
        pdf_generator = PDFGenerator()
        pdf_bytes = pdf_generator.generate(report)

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
