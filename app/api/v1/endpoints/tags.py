from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from schemas.common import ApiListResponseModel, ApiResponseModel, api_list_response, api_response
from schemas.dto import SentimentStatsDTO
from schemas.tag import (
    CategoryCreate,
    TagCreate,
    TagUpdate,
)
from services.tag_service import SentimentService, TagService
from .deps import get_sentiment_service, get_tag_service

router = APIRouter(tags=["tags"])
sentiment_router = APIRouter(tags=["sentiment"])

@router.get("/categories", response_model=ApiListResponseModel[dict])
async def api_categories(
    is_active: bool = Query(True), service: TagService = Depends(get_tag_service)
) -> dict[str, Any]:
    """카테고리 목록"""
    categories = await service.get_categories(is_active=is_active)
    return api_list_response(categories)


@router.post("/categories", status_code=201, response_model=ApiResponseModel[dict])
async def api_create_category(
    data: CategoryCreate, service: TagService = Depends(get_tag_service)
) -> dict[str, Any]:
    """카테고리 생성"""
    result = await service.create_category(data.model_dump())
    return api_response(result)

@router.get("/list", response_model=ApiListResponseModel[dict])
async def api_tags(
    group_name: str | None = Query(None),
    category_id: int | None = Query(None),
    sentiment: str | None = Query(None),
    is_active: bool = Query(True, description="활성 태그만 조회"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    service: TagService = Depends(get_tag_service),
) -> dict[str, Any]:
    """태그 목록"""
    tags, total = await service.get_tags(
        category_id=category_id,
        sentiment=sentiment,
        group_name=group_name,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )
    return api_list_response(tags, total=total, limit=limit, offset=offset)

@router.post("/batch", response_model=ApiResponseModel[dict])
async def api_tags_batch(
    branch_ids: list[int] = Body(..., embed=True),
    period: str = Body("all", embed=True),
    service: TagService = Depends(get_tag_service),
) -> dict[str, Any]:
    """여러 지점의 top3 태그 일괄 조회"""
    if not branch_ids:
        return api_response({})

    tags = await service.get_batch_tags(branch_ids, period_type=period)
    return api_response(tags)

@router.post("/", status_code=201, response_model=ApiResponseModel[dict])
async def api_create_tag(
    data: TagCreate, service: TagService = Depends(get_tag_service)
) -> dict[str, Any]:
    """태그 생성"""
    result = await service.create_tag(data.model_dump())
    return api_response(result)


@router.put("/{tag_id}", response_model=ApiResponseModel[dict])
async def api_update_tag(
    tag_id: int, data: TagUpdate, service: TagService = Depends(get_tag_service)
) -> dict[str, Any]:
    """태그 수정"""
    update_data = data.model_dump(exclude_unset=True)
    result = await service.update_tag(tag_id, update_data)
    return api_response(result)


@router.delete("/{tag_id}", response_model=ApiResponseModel[dict])
async def api_delete_tag(
    tag_id: int, service: TagService = Depends(get_tag_service)
) -> dict[str, Any]:
    """태그 삭제"""
    await service.delete_tag(tag_id)
    return api_response()


# ============================================================
# Sentiment (별도 prefix /sentiment 로 등록)
# ============================================================


@sentiment_router.get("/stats", response_model=ApiResponseModel[SentimentStatsDTO])
async def api_sentiment_stats(
    branch_id: int | None = Query(None),
    service: SentimentService = Depends(get_sentiment_service),
) -> dict[str, Any]:
    """지점별 감정태그 통계"""
    result = await service.get_stats(branch_id)
    return api_response(result.model_dump(by_alias=True))


@sentiment_router.get("/stats/all", response_model=ApiListResponseModel[dict])
async def api_all_sentiment_stats(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    service: SentimentService = Depends(get_sentiment_service),
) -> dict[str, Any]:
    """전체 지점 감정통계 목록 (페이지네이션)"""
    stats, total = await service.get_all_stats(page=page, limit=limit)
    offset = (page - 1) * limit
    return api_list_response(stats, total=total, limit=limit, offset=offset)
