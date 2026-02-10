"""
감정태그 통계 API (FastAPI)

Router: /api/sentiment
담당: HTTP 요청/응답 처리만
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from services.sentiment_service import SentimentService

from .deps import get_sentiment_service

router = APIRouter(tags=["sentiment"])


@router.get("/stats")
async def api_sentiment_stats(
    branch_id: int | None = Query(None),
    service: SentimentService = Depends(get_sentiment_service),
) -> dict[str, Any]:
    """지점별 감정태그 통계"""
    result = await service.get_stats(branch_id)
    return result.to_dict()


@router.get("/stats/all")
async def api_all_sentiment_stats(
    service: SentimentService = Depends(get_sentiment_service),
) -> list[dict[str, Any]]:
    """전체 지점 감정통계 목록"""
    return await service.get_all_stats()
