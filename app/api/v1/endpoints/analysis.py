"""
리뷰 분석 페이지 API

Router: /api/analysis
담당: HTTP 요청/응답 처리만
"""

from __future__ import annotations

import logging
from urllib.parse import quote

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from schemas.analysis import ReviewFilterParams
from schemas.common import api_response
from services.analysis_service import AnalysisService

from .deps import get_analysis_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analysis"])


@router.get("/filters")
async def api_get_filter_options(
    service: AnalysisService = Depends(get_analysis_service),
) -> dict[str, Any]:
    """필터 옵션 조회 (지역, 업체명, 지점 목록)"""
    try:
        result = await service.get_filter_options()
        return api_response(result.to_dict())

    except Exception as e:
        logger.error(f"Failed to get filter options: {e}")
        raise HTTPException(
            status_code=500,
            detail="필터 옵션을 불러오는데 실패했습니다.",
        )


@router.get("/reviews")
async def api_get_reviews(
    filters: ReviewFilterParams = Depends(),
    limit: int = Query(20, ge=1, le=100, description="조회 개수 (기본 20, 최대 100)"),
    offset: int = Query(0, ge=0, description="페이징 오프셋"),
    is_new: bool | None = Query(None, description="신규 리뷰 필터 (true: 신규만, false: 읽은 것만)"),
    service: AnalysisService = Depends(get_analysis_service),
) -> dict[str, Any]:
    """필터링된 리뷰 조회"""
    try:
        result = await service.get_filtered_reviews(
            regions=filters.regions,
            companies=filters.companies,
            branch_ids=filters.branch_ids,
            sentiment=filters.sentiment,
            date_from=filters.date_from,
            date_to=filters.date_to,
            sort_by=filters.sort_by,
            limit=limit,
            offset=offset,
            is_new=is_new,
        )
        return api_response(result.to_dict())

    except Exception as e:
        logger.error(f"Failed to get filtered reviews: {e}")
        raise HTTPException(
            status_code=500,
            detail="리뷰를 불러오는데 실패했습니다.",
        )


@router.get("/reviews/export")
async def api_export_reviews_to_excel(
    filters: ReviewFilterParams = Depends(),
    service: AnalysisService = Depends(get_analysis_service),
) -> StreamingResponse:
    """필터링된 리뷰를 엑셀 파일로 내보내기"""
    try:
        output, filename = await service.export_to_excel(
            regions=filters.regions,
            companies=filters.companies,
            branch_ids=filters.branch_ids,
            sentiment=filters.sentiment,
            date_from=filters.date_from,
            date_to=filters.date_to,
            sort_by=filters.sort_by,
        )

        encoded_filename = quote(filename)

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            },
        )

    except Exception as e:
        logger.error(f"Failed to export reviews: {e}")
        raise HTTPException(
            status_code=500,
            detail="리뷰 내보내기에 실패했습니다.",
        )
