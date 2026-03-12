"""
감정태그 통계 API (FastAPI)

Router: /api/sentiment
담당: HTTP 요청/응답 처리만
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from schemas.common import ApiListResponseModel, ApiResponseModel, api_list_response, api_response
from schemas.dto import SentimentStatsDTO
from services.sentiment_service import SentimentService

from .deps import get_sentiment_service

router = APIRouter(tags=["sentiment"])


@router.get("/stats", response_model=ApiResponseModel[SentimentStatsDTO])
async def api_sentiment_stats(
    branch_id: int | None = Query(None),
    service: SentimentService = Depends(get_sentiment_service),
) -> dict[str, Any]:
    """지점별 감정태그 통계"""
    result = await service.get_stats(branch_id)
    return api_response(result.model_dump(by_alias=True))


@router.get("/stats/all", response_model=ApiListResponseModel[dict])
async def api_all_sentiment_stats(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    service: SentimentService = Depends(get_sentiment_service),
) -> dict[str, Any]:
    """전체 지점 감정통계 목록 (페이지네이션)"""
    stats, total = await service.get_all_stats(page=page, limit=limit)
    offset = (page - 1) * limit
    return api_list_response(stats, total=total, limit=limit, offset=offset)
