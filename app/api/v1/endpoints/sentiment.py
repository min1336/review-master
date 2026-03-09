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
        raise HTTPException(status_code=500, detail="감정태그 통계 조회 중 오류가 발생했습니다") from e


@router.get("/stats/all", response_model=ApiListResponseModel[dict])
async def api_all_sentiment_stats(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    service: SentimentService = Depends(get_sentiment_service),
) -> dict[str, Any]:
    """전체 지점 감정통계 목록 (페이지네이션)"""
    try:
        stats, total = await service.get_all_stats(page=page, limit=limit)
        offset = (page - 1) * limit
        return api_list_response(stats, total=total, limit=limit, offset=offset)
    except Exception as e:
        logger.exception("전체 감정통계 조회 오류")
        raise HTTPException(status_code=500, detail="전체 감정통계 조회 중 오류가 발생했습니다") from e
