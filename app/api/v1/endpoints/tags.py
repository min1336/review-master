"""
태그/카테고리/매핑 API (FastAPI)

Router: /api/tags
담당: HTTP 요청/응답 처리만
"""
import asyncio
from typing import Optional, List

from fastapi import APIRouter, Query, HTTPException, Depends, Body

from schemas.tag import (
    TagCreate, TagUpdate, CategoryCreate, CategoryUpdate,
    KeywordMappingCreate, BulkMappingRequest, TagAnalysisRequest
)
from services.tag_service import TagService
from services.summary_service import SummaryService
from .deps import get_tag_service, get_summary_service

router = APIRouter(tags=["tags"])


# ============================================================
# 태그 분석 테스트
# ============================================================

@router.post("/analyze-tags")
async def api_analyze_tags(
    data: TagAnalysisRequest,
    service: TagService = Depends(get_tag_service)
):
    """리뷰 텍스트의 태그 분석 테스트"""
    try:
        result = await service.analyze_tags(data.review)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 카테고리 관리
# ============================================================

@router.get("/categories")
async def api_categories(
    is_active: bool = Query(True),
    service: TagService = Depends(get_tag_service)
):
    """카테고리 목록"""
    return await service.get_categories(is_active=is_active)


@router.get("/categories/{category_id}")
async def api_category_detail(
    category_id: int,
    service: TagService = Depends(get_tag_service)
):
    """카테고리 상세"""
    category = await service.get_category(category_id)
    if category:
        return category
    raise HTTPException(status_code=404, detail="Category not found")


@router.post("/categories", status_code=201)
async def api_create_category(
    data: CategoryCreate,
    service: TagService = Depends(get_tag_service)
):
    """카테고리 생성"""
    try:
        result = await service.create_category(data.model_dump())
        return {'success': True, 'data': result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/categories/{category_id}")
async def api_update_category(
    category_id: int,
    data: CategoryUpdate,
    service: TagService = Depends(get_tag_service)
):
    """카테고리 수정"""
    update_data = data.model_dump(exclude_unset=True)
    result = await service.update_category(category_id, update_data)
    return {'success': True, 'data': result}


@router.delete("/categories/{category_id}")
async def api_delete_category(
    category_id: int,
    service: TagService = Depends(get_tag_service)
):
    """카테고리 삭제"""
    result = await service.delete_category(category_id)
    return {'success': result}


# ============================================================
# 태그 관리
# ============================================================

@router.get("/list")
async def api_tags(
    group_name: Optional[str] = Query(None),
    category_id: Optional[int] = Query(None),
    sentiment: Optional[str] = Query(None),
    service: TagService = Depends(get_tag_service)
):
    """태그 목록"""
    return await service.get_tags(
        category_id=category_id,
        sentiment=sentiment,
        group_name=group_name
    )


@router.get("/groups")
async def api_tag_groups(
    service: TagService = Depends(get_tag_service)
):
    """태그 그룹 목록"""
    return await service.get_tag_groups()


@router.get("/{tag_id}")
async def api_tag_detail(
    tag_id: int,
    service: TagService = Depends(get_tag_service)
):
    """태그 상세"""
    tag = await service.get_tag(tag_id)
    if tag:
        return tag
    raise HTTPException(status_code=404, detail="Tag not found")


@router.post("/", status_code=201)
async def api_create_tag(
    data: TagCreate,
    service: TagService = Depends(get_tag_service)
):
    """태그 생성"""
    try:
        result = await service.create_tag(data.model_dump())
        return {'success': True, 'data': result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{tag_id}")
async def api_update_tag(
    tag_id: int,
    data: TagUpdate,
    service: TagService = Depends(get_tag_service)
):
    """태그 수정"""
    update_data = data.model_dump(exclude_unset=True)
    result = await service.update_tag(tag_id, update_data)
    return {'success': True, 'data': result}


@router.delete("/{tag_id}")
async def api_delete_tag(
    tag_id: int,
    service: TagService = Depends(get_tag_service)
):
    """태그 삭제"""
    result = await service.delete_tag(tag_id)
    return {'success': result}


@router.get("/{tag_id}/keywords")
async def api_tag_keywords(
    tag_id: int,
    service: TagService = Depends(get_tag_service)
):
    """태그에 매핑된 키워드 목록"""
    return await service.get_mappings(tag_id=tag_id)


# ============================================================
# 키워드-태그 매핑
# ============================================================

@router.get("/mappings")
async def api_mappings(
    tag_id: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    service: TagService = Depends(get_tag_service)
):
    """키워드-태그 매핑 목록"""
    return await service.get_mappings(tag_id=tag_id, keyword=keyword)


@router.post("/mappings", status_code=201)
async def api_create_mapping(
    data: KeywordMappingCreate,
    service: TagService = Depends(get_tag_service)
):
    """키워드 → 태그 매핑 생성"""
    try:
        result = await service.create_mapping(
            keyword=data.keyword,
            tag_id=data.tag_id,
            is_auto=data.is_auto
        )
        return {'success': True, 'data': result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/mappings/{mapping_id}")
async def api_delete_mapping(
    mapping_id: int,
    service: TagService = Depends(get_tag_service)
):
    """매핑 삭제"""
    result = await service.delete_mapping(mapping_id)
    return {'success': result}


@router.get("/mappings/unmapped")
async def api_unmapped_keywords(
    limit: int = Query(100, ge=1, le=1000),
    service: TagService = Depends(get_tag_service)
):
    """매핑되지 않은 키워드 목록"""
    return await service.get_unmapped_keywords(limit=limit)


@router.post("/mappings/bulk")
async def api_bulk_mappings(
    data: BulkMappingRequest,
    service: TagService = Depends(get_tag_service)
):
    """키워드 매핑 일괄 생성"""
    mappings = [m.model_dump() for m in data.mappings]
    count = await service.bulk_create_mappings(mappings)
    return {'success': True, 'created': count}


@router.post("/mappings/auto")
async def api_auto_mapping():
    """자동 매핑 실행"""
    try:
        def auto_map():
            from analysis import TagMapper
            mapper = TagMapper()
            return mapper.auto_map_all_keywords()

        result = await asyncio.to_thread(auto_map)
        return {'success': True, **result}
    except ImportError:
        raise HTTPException(status_code=500, detail="TagMapper module not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 지점별 태그 조회 (branches.py에서 이동)
# ============================================================

@router.get("/branch/{branch_id}")
async def api_branch_tags(
    branch_id: int,
    period: str = Query("all", description="기간 필터 (all, 1m, 3m, 6m, 1y)"),
    limit: int = Query(10, ge=1, le=100),
    service: TagService = Depends(get_tag_service)
):
    """지점별 태그 목록"""
    return await service.get_branch_tags(branch_id, period_type=period, limit=limit)


@router.post("/batch")
async def api_tags_batch(
    branch_ids: List[int] = Body(..., embed=True),
    service: TagService = Depends(get_tag_service)
):
    """
    여러 지점의 top3 태그 일괄 조회
    POST body: {"branch_ids": [1, 2, 3, ...]}
    """
    if not branch_ids:
        return {}

    return await service.get_batch_tags(branch_ids)


@router.get("/branch/{branch_id}/summary")
async def api_branch_summary(
    branch_id: int,
    service: SummaryService = Depends(get_summary_service)
):
    """지점별 요약 조회"""
    summary = await service.get_summary(branch_id)
    if summary:
        return summary
    raise HTTPException(status_code=404, detail="Not found")
