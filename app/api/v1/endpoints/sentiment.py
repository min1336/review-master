"""
감정태그 통계 API (FastAPI)

Router: /api/sentiment
담당: HTTP 요청/응답 처리만
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from schemas.common import ApiListResponseModel, ApiResponseModel, api_list_response, api_response
from schemas.dto import SentimentStatsDTO
from services.sentiment_service import SentimentService

from .deps import get_sentiment_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sentiment"])


@router.get("/stats", response_model=ApiResponseModel[SentimentStatsDTO])
async def api_sentiment_stats(
    branch_id: int | None = Query(None),
    service: SentimentService = Depends(get_sentiment_service),
) -> dict[str, Any]:
    """지점별 감정태그 통계"""
    try:
        result = await service.get_stats(branch_id)
        return api_response(result.model_dump(by_alias=True))
    except Exception as e:
        logger.exception("감정태그 통계 조회 오류")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/stats/all", response_model=ApiListResponseModel[dict])
async def api_all_sentiment_stats(
    service: SentimentService = Depends(get_sentiment_service),
) -> dict[str, Any]:
    """전체 지점 감정통계 목록"""
    try:
        stats = await service.get_all_stats()
        return api_list_response(stats)
    except Exception as e:
        logger.exception("전체 감정통계 조회 오류")
        raise HTTPException(status_code=500, detail=str(e)) from e
