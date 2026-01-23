"""
통합 요약 API (FastAPI)

Router: /api/v2
담당: HTTP 요청/응답 처리만 (비즈니스 로직은 Service에서)

주요 엔드포인트:
- GET /summaries: 업체 목록 조회 (날짜 필터링 지원)
- GET /summaries/{branch_id}/reviews: 지점별 리뷰 목록 (날짜 필터링 지원)
"""
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Query, HTTPException, Depends

from schemas.summary import SummaryUpdate, StatusUpdate, RegenerateRequest
from services.summary_service import SummaryService
from .deps import get_summary_service

router = APIRouter(prefix="/v2", tags=["summaries"])


@router.get("/summaries")
async def api_summaries(
    status: Optional[str] = Query(None, description="상태 필터 (draft, approved, published)"),
    region: Optional[str] = Query(None, description="지역 필터"),
    keyword: Optional[str] = Query(None, description="키워드/업체명 검색"),
    min_rating: Optional[float] = Query(None, description="최소 평점"),
    max_rating: Optional[float] = Query(None, description="최대 평점"),
    min_reviews: int = Query(30, description="최소 리뷰 수"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("branch_id"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    review_date_from: Optional[str] = Query(
        None,
        description="시작일 (YYYY-MM-DD) - 이 기간에 리뷰가 있는 업체만 표시"
    ),
    review_date_to: Optional[str] = Query(
        None,
        description="종료일 (YYYY-MM-DD) - 이 기간에 리뷰가 있는 업체만 표시"
    ),
    service: SummaryService = Depends(get_summary_service)
):
    """
    통합 요약 목록 조회

    날짜 필터 사용 시:
    - review_date_from ~ review_date_to 기간에 리뷰가 있는 업체만 반환
    - 종료일은 해당일 23:59:59까지 포함
    """
    # 날짜 문자열 → datetime 파싱
    parsed_date_from = None
    parsed_date_to = None

    if review_date_from:
        parsed_date_from = datetime.strptime(review_date_from, "%Y-%m-%d")
    if review_date_to:
        # 종료일은 해당일 전체를 포함하도록 23:59:59로 설정
        parsed_date_to = datetime.strptime(review_date_to, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59
        )

    return await service.get_summaries(
        status=status,
        region=region,
        keyword=keyword,
        min_rating=min_rating,
        max_rating=max_rating,
        min_reviews=min_reviews,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        order=order,
        review_date_from=parsed_date_from,
        review_date_to=parsed_date_to
    )


@router.get("/summaries/{branch_id}")
async def api_summary_detail(
    branch_id: int,
    service: SummaryService = Depends(get_summary_service)
):
    """특정 지점 요약 상세"""
    summary = await service.get_summary(branch_id)
    if summary:
        return summary
    raise HTTPException(status_code=404, detail="Not found")


@router.put("/summaries/{branch_id}")
async def api_update_summary(
    branch_id: int,
    data: SummaryUpdate,
    service: SummaryService = Depends(get_summary_service)
):
    """요약 수정"""
    update_data = data.model_dump(exclude_unset=True)
    result = await service.update_summary(branch_id, update_data)
    return {'success': True, 'data': result}


@router.put("/summaries/{branch_id}/status")
async def api_update_status(
    branch_id: int,
    data: StatusUpdate,
    service: SummaryService = Depends(get_summary_service)
):
    """요약 상태 변경"""
    result = await service.update_status(branch_id, data.status)
    return {'success': True, 'data': result}


@router.post("/summaries/{branch_id}/regenerate")
async def api_regenerate_summary(
    branch_id: int,
    data: RegenerateRequest = None,
    service: SummaryService = Depends(get_summary_service)
):
    """AI 요약 재생성 (pending에 저장, 바로 적용 안 됨)"""
    period = data.period if data else "all"

    try:
        summary = await service.regenerate_summary(branch_id, period)
        return {'success': True, 'summary': summary, 'period': period, 'pending': True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/summaries/{branch_id}/apply-pending")
async def api_apply_pending_summary(
    branch_id: int,
    data: RegenerateRequest = None,
    service: SummaryService = Depends(get_summary_service)
):
    """대기 중인 요약 적용 (pending → main)"""
    period = data.period if data else "all"

    try:
        result = await service.apply_pending_summary(branch_id, period)
        return {'success': True, **result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/summaries/{branch_id}/discard-pending")
async def api_discard_pending_summary(
    branch_id: int,
    data: RegenerateRequest = None,
    service: SummaryService = Depends(get_summary_service)
):
    """대기 중인 요약 취소 (삭제)"""
    period = data.period if data else "all"

    try:
        result = await service.discard_pending_summary(branch_id, period)
        return {'success': True, **result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/stats")
async def api_stats(
    service: SummaryService = Depends(get_summary_service)
):
    """요약 통계"""
    return await service.get_stats()


@router.get("/stats/region")
async def api_region_stats(
    service: SummaryService = Depends(get_summary_service)
):
    """지역별 통계"""
    return await service.get_region_stats()


@router.get("/stats/rating")
async def api_rating_stats(
    service: SummaryService = Depends(get_summary_service)
):
    """평점 분포 통계"""
    return await service.get_rating_stats()


@router.get("/summaries/{branch_id}/reviews")
async def api_branch_reviews(
    branch_id: int,
    car_model: Optional[str] = Query(None, description="차량 모델 필터"),
    sentiment: Optional[str] = Query(None, description="감정 필터 (positive, neutral, negative)"),
    review_date_from: Optional[str] = Query(
        None,
        description="시작일 (YYYY-MM-DD) - 이 날짜 이후 리뷰만 조회"
    ),
    review_date_to: Optional[str] = Query(
        None,
        description="종료일 (YYYY-MM-DD) - 이 날짜 이전 리뷰만 조회"
    ),
    limit: int = Query(100, ge=1, le=500, description="조회 개수"),
    offset: int = Query(0, ge=0, description="오프셋"),
    service: SummaryService = Depends(get_summary_service)
):
    """
    지점별 리뷰 목록 조회 (필터링 지원)

    branch_reviews 테이블에서 원본 리뷰를 조회합니다.

    필터 옵션:
    - car_model: 차량 모델
    - sentiment: 감정 (positive, neutral, negative)
    - review_date_from ~ review_date_to: 날짜 범위 (종료일은 23:59:59까지 포함)
    """
    # 날짜 파싱
    parsed_date_from = None
    parsed_date_to = None

    if review_date_from:
        parsed_date_from = datetime.strptime(review_date_from, "%Y-%m-%d")
    if review_date_to:
        parsed_date_to = datetime.strptime(review_date_to, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59
        )

    result = await service.get_branch_reviews(
        branch_id=branch_id,
        car_model=car_model,
        sentiment=sentiment,
        review_date_from=parsed_date_from,
        review_date_to=parsed_date_to,
        limit=limit,
        offset=offset
    )
    return result


@router.get("/summaries/{branch_id}/detail")
async def api_branch_detail(
    branch_id: int,
    include_summaries: bool = Query(True, description="기간별 요약 포함 여부"),
    max_reviews: int = Query(500, ge=1, le=1000, description="최대 리뷰 수"),
    service: SummaryService = Depends(get_summary_service)
):
    """
    지점 상세 분석 (JSON)

    - 리뷰별 키워드 추출
    - 태그+감정 분류
    - 기간별 요약
    """
    result = await service.get_branch_detail(
        branch_id=branch_id,
        include_summaries=include_summaries,
        max_reviews=max_reviews
    )
    if result:
        return result
    raise HTTPException(status_code=404, detail="Branch not found")
