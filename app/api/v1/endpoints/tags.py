"""
태그/카테고리 API (FastAPI)

Router: /api/tags
담당: HTTP 요청/응답 처리만

라우트 순서 원칙:
  고정 경로 → path parameter 경로 (FastAPI가 위→아래 순서로 매칭)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from schemas.tag import (
    CategoryCreate,
    TagAnalysisRequest,
    TagCreate,
    TagUpdate,
)
from services.tag_service import TagService

from .deps import get_tag_service

router = APIRouter(tags=["tags"])


# ================================================================
# 1. 분석
# ================================================================


@router.post("/analyze-tags")
async def api_analyze_tags(
    data: TagAnalysisRequest, service: TagService = Depends(get_tag_service)
) -> dict[str, Any]:
    """리뷰 텍스트의 태그 분석 테스트"""
    try:
        result = await service.analyze_tags(data.review)
        return {"success": True, "data": result.to_dict()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# ================================================================
# 2. 카테고리 (목록 + 생성)
# ================================================================


@router.get("/categories")
async def api_categories(
    is_active: bool = Query(True), service: TagService = Depends(get_tag_service)
) -> dict[str, Any]:
    """카테고리 목록"""
    categories = await service.get_categories(is_active=is_active)
    return {"success": True, "data": categories, "count": len(categories)}


@router.post("/categories", status_code=201)
async def api_create_category(
    data: CategoryCreate, service: TagService = Depends(get_tag_service)
) -> dict[str, Any]:
    """카테고리 생성"""
    try:
        result = await service.create_category(data.model_dump())
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ================================================================
# 3. 태그 목록 (고정 경로)
# ================================================================


@router.get("/list")
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
    tags = await service.get_tags(
        category_id=category_id,
        sentiment=sentiment,
        group_name=group_name,
        is_active=is_active,
    )
    total = len(tags)
    paginated = tags[offset : offset + limit]
    return {"success": True, "data": paginated, "count": total}


# ================================================================
# 4. 지점별 태그 일괄 조회 (고정 경로)
# ================================================================


@router.post("/batch")
async def api_tags_batch(
    branch_ids: list[int] = Body(..., embed=True),
    period: str = Body("all", embed=True),
    service: TagService = Depends(get_tag_service),
) -> dict[str, Any]:
    """여러 지점의 top3 태그 일괄 조회"""
    if not branch_ids:
        return {"success": True, "data": {}}

    tags = await service.get_batch_tags(branch_ids, period_type=period)
    return {"success": True, "data": tags}


# ================================================================
# 5. 태그 CRUD (path parameter — 맨 마지막)
# ================================================================


@router.post("/", status_code=201)
async def api_create_tag(
    data: TagCreate, service: TagService = Depends(get_tag_service)
) -> dict[str, Any]:
    """태그 생성"""
    try:
        result = await service.create_tag(data.model_dump())
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.put("/{tag_id}")
async def api_update_tag(
    tag_id: int, data: TagUpdate, service: TagService = Depends(get_tag_service)
) -> dict[str, Any]:
    """태그 수정"""
    update_data = data.model_dump(exclude_unset=True)
    result = await service.update_tag(tag_id, update_data)
    return {"success": True, "data": result}


@router.delete("/{tag_id}")
async def api_delete_tag(
    tag_id: int, service: TagService = Depends(get_tag_service)
) -> dict[str, Any]:
    """태그 삭제"""
    await service.delete_tag(tag_id)
    return {"success": True}
