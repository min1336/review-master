"""
감정태그 통계 및 리뷰 API (FastAPI)

Router: /api/sentiment
담당: HTTP 요청/응답 처리만
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from schemas.common import CleanupRequest
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


@router.get("/reviews/recent")
async def api_recent_reviews(
    sentiment: str | None = Query(None, pattern="^(positive|negative|neutral)$"),
    branch_id: int | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    service: SentimentService = Depends(get_sentiment_service),
) -> dict[str, Any]:
    """최근 리뷰 검색 (1개월치)"""
    result = await service.search_reviews(
        sentiment=sentiment, branch_id=branch_id, limit=limit, offset=offset
    )
    return result.to_dict()


@router.post("/reviews/cleanup")
async def api_cleanup_reviews(
    data: CleanupRequest = None,
    service: SentimentService = Depends(get_sentiment_service),
) -> dict[str, Any]:
    """리뷰 정리 (1개월 이전 삭제 + 지점당 30개 제한)"""
    days = data.days if data else 30
    max_per_branch = data.max_per_branch if data else 30

    result = await service.cleanup_reviews(days=days, max_per_branch=max_per_branch)
    return {
        **result.to_dict(),
        "message": (
            f"{days}일 이전 {result.old_deleted}개, "
            f"지점당 초과분 {result.excess_deleted}개 삭제됨"
        ),
    }
