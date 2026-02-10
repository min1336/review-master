"""Public Report API 엔드포인트

X-API-Key 인증으로 AI 리포트를 외부에 제공합니다.
차량별 평가 분석은 기본 긍정 Top 5, URL 파라미터로 조절 가능합니다.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from schemas.common import api_response

from .deps import get_report_service, require_public_api_key

logger = logging.getLogger(__name__)

router = APIRouter(tags=["public-report"])

DEFAULT_VEHICLE_TOP_N = 5


@router.get("/{branch_id}")
async def get_public_report(
    branch_id: int,
    start_date: str = Query(..., description="시작일 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="종료일 (YYYY-MM-DD)"),
    vehicle_top: int = Query(
        default=DEFAULT_VEHICLE_TOP_N,
        ge=1,
        le=100,
        description="차량별 평가 상위 N개 (기본 5, 긍정 호평률 순)",
    ),
    _: None = Depends(require_public_api_key),
    service: "ReportService" = Depends(get_report_service),
) -> dict[str, Any]:
    """
    AI 리포트 조회 (Public)

    - X-API-Key 헤더 필요
    - 저장된 리포트 우선, 없으면 신규 생성
    - vehicle_top: 차량별 평가를 호평률 상위 N개로 제한 (기본 5)
    """
    from datetime import datetime

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format. Expected YYYY-MM-DD: {e}",
        ) from e

    if start_dt > end_dt:
        raise HTTPException(status_code=400, detail="시작일이 종료일보다 늦을 수 없습니다.")

    try:
        report, _is_new = await service.get_or_generate_report(
            branch_id=branch_id,
            start_date=start_dt,
            end_date=end_dt,
        )

        # 지역 정보 조회 (Summary 응답과 동일 필드 제공)
        summary = await service.summary_repo.get_by_branch_id(branch_id)
        region = summary.region if summary else ""

        # 차량별 평가: 건수(count) 내림차순 상위 N개
        sorted_vehicles = sorted(
            report.vehicle_analysis, key=lambda v: v.count, reverse=True,
        )
        top_vehicles = [
            {
                "model": v.model,
                "count": v.count,
                "like_ratio": v.like_ratio,
                "dislike_ratio": v.dislike_ratio,
                "top_praise": v.top_praise,
                "top_issue": v.top_issue,
            }
            for v in sorted_vehicles[:vehicle_top]
        ]

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
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Public report fetch failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e
