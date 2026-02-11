"""Public Summary API 엔드포인트"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from schemas.common import api_response
from services.summary_service import SummaryService

from .deps import get_summary_service, require_public_api_key

logger = logging.getLogger(__name__)

router = APIRouter(tags=["public-summary"])


def _pick_latest_summary(summary) -> str | None:
    """요약 문자열 선택 (가장 최신/짧은 기간 우선)"""
    candidates = [
        summary.summary_1m,
        summary.summary_3m,
        summary.summary_6m,
        summary.summary_1y,
        summary.summary_all,
    ]
    for value in candidates:
        if value and str(value).strip():
            return value
    return None


@router.get("/{branch_id}")
async def get_public_summary(
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
            "status": summary.status,
            "review_count": summary.review_count,
            "avg_rating": summary.avg_rating,
            "updated_at": summary.updated_at,
        }

        if summary.status == "published":
            latest = _pick_latest_summary(summary)
            if not latest:
                raise HTTPException(status_code=404, detail="Summary content not available")
            data["summary"] = latest
        else:
            data["summary"] = "요약이 대기중입니다."

        return api_response(data)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Public summary fetch failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e
