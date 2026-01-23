"""
감정태그 통계 및 리뷰 API (FastAPI)

Router: /api/sentiment
담당: HTTP 요청/응답 처리만
"""
from typing import Optional

from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel

from services.sentiment_service import SentimentService
from .deps import get_sentiment_service

router = APIRouter(tags=["sentiment"])


class CleanupRequest(BaseModel):
    """리뷰 정리 요청"""
    days: int = 30
    max_per_branch: int = 30


@router.get("/stats")
async def api_sentiment_stats(
    branch_id: Optional[int] = Query(None),
    service: SentimentService = Depends(get_sentiment_service)
):
    """지점별 감정태그 통계"""
    return await service.get_stats(branch_id)


@router.get("/stats/all")
async def api_all_sentiment_stats(
    service: SentimentService = Depends(get_sentiment_service)
):
    """전체 지점 감정통계 목록"""
    return await service.get_all_stats()


@router.get("/reviews/recent")
async def api_recent_reviews(
    sentiment: Optional[str] = Query(None, pattern="^(positive|negative|neutral)$"),
    branch_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    service: SentimentService = Depends(get_sentiment_service)
):
    """최근 리뷰 검색 (1개월치)"""
    return await service.search_reviews(
        sentiment=sentiment,
        branch_id=branch_id,
        limit=limit,
        offset=offset
    )


@router.post("/reviews/cleanup")
async def api_cleanup_reviews(
    data: CleanupRequest = None,
    service: SentimentService = Depends(get_sentiment_service)
):
    """리뷰 정리 (1개월 이전 삭제 + 지점당 30개 제한)"""
    days = data.days if data else 30
    max_per_branch = data.max_per_branch if data else 30

    result = await service.cleanup_reviews(days=days, max_per_branch=max_per_branch)
    return {
        **result,
        'message': f'{days}일 이전 {result["old_deleted"]}개, 지점당 초과분 {result["excess_deleted"]}개 삭제됨'
    }
