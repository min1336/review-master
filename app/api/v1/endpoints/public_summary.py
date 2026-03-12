"""Public Summary API 엔드포인트"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from schemas.common import ApiResponseModel, api_response
from services.summary_service import SummaryService

from .deps import get_summary_service, require_public_api_key

router = APIRouter(tags=["public-summary"])


@router.get("/{branch_id}", response_model=ApiResponseModel[dict])
async def api_get_public_summary(
    branch_id: int,
    _: None = Depends(require_public_api_key),
    service: SummaryService = Depends(get_summary_service),
) -> dict[str, Any]:
    """
    최신 요약 1개 조회 (Public)

    - X-API-Key 헤더 필요
    """
    try:
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
    except HTTPException:
        raise
