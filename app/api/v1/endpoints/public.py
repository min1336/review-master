"""Public API 엔드포인트

X-API-Key 인증으로 요약/리포트를 외부에 제공합니다.
- summary_router: /review/*, /public/* — 요약 조회
- report_router: /public/report/* — AI 리포트 조회
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from core.timezone import date_to_utc
from schemas.common import ApiResponseModel, api_response, validate_date_range_d
from services.report_service import ReportService
from services.summary_service import SummaryService

from .deps import get_report_service, get_summary_service, require_public_api_key

# ============================================================
# Public Summary
# ============================================================

summary_router = APIRouter(tags=["public-summary"])


@summary_router.get("/{branch_id}", response_model=ApiResponseModel[dict])
async def api_get_public_summary(
    branch_id: int,
    _: None = Depends(require_public_api_key),
    service: SummaryService = Depends(get_summary_service),
) -> dict[str, Any]:
    """
    최신 요약 1개 조회 (Public)

    - X-API-Key 헤더 필요
    """
    summary = await service.get_summary_by_branch_id(branch_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")

    data = {
        "branch_id": summary.branch_id,
        "branch_name": summary.branch_name,
        "region": summary.region,
        "review_count": summary.review_count,
        "avg_rating": summary.avg_rating,
        "updated_at": summary.updated_at,
    }

    latest = SummaryService.pick_latest_summary(summary)
    data["summary"] = latest or "요약이 아직 생성되지 않았습니다."

    return api_response(data)


# ============================================================
# Public Report
# ============================================================

report_router = APIRouter(tags=["public-report"])

DEFAULT_VEHICLE_TOP_N = 5


@report_router.get("/{branch_id}", response_model=ApiResponseModel[dict])
async def api_get_public_report(
    branch_id: int,
    start_date: date = Query(..., description="시작일 (YYYY-MM-DD)"),
    end_date: date = Query(..., description="종료일 (YYYY-MM-DD)"),
    vehicle_top: int = Query(
        default=DEFAULT_VEHICLE_TOP_N,
        ge=1,
        le=100,
        description="차량별 평가 상위 N개 (기본 5, 긍정 호평률 순)",
    ),
    _: None = Depends(require_public_api_key),
    service: ReportService = Depends(get_report_service),
) -> dict[str, Any]:
    """
    AI 리포트 조회 (Public)

    - X-API-Key 헤더 필요
    - 저장된 리포트 우선, 없으면 신규 생성
    - vehicle_top: 차량별 평가를 호평률 상위 N개로 제한 (기본 5)
    """
    validate_date_range_d(start_date, end_date)

    try:
        report, _is_new = await service.get_or_generate_report(
            branch_id=branch_id,
            start_date=date_to_utc(start_date),
            end_date=date_to_utc(end_date, end_of_day=True),
        )

        # 지역 정보 조회 (Summary 응답과 동일 필드 제공)
        region = await service.get_branch_region(branch_id)

        # 차량별 평가: 건수(count) 내림차순 상위 N개
        top_vehicles = ReportService.get_top_vehicles(
            report.vehicle_analysis, top_n=vehicle_top,
        )

        return api_response({
            "branch_id": report.branch_id,
            "branch_name": report.branch_name,
            "region": region,
            "period": f"{report.period_start} ~ {report.period_end}",
            "total_reviews": report.total_reviews,
            "period_summary": report.period_summary,
            "vehicle_analysis": top_vehicles,
            "vehicle_total_count": len(report.vehicle_analysis),
            "vehicle_top": vehicle_top,
            "generated_at": report.generated_at,
        })
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
