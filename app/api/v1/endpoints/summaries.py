"""
통합 요약 API (FastAPI)

Router: /api/v2
담당: HTTP 요청/응답 처리만 (비즈니스 로직은 Service에서)

주요 엔드포인트:
- GET /summaries: 업체 목록 조회 (날짜 필터링 지원)
- GET /summaries/{branch_id}/reviews: 지점별 리뷰 목록 (날짜 필터링 지원)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from schemas.dto import BranchCarModelsDTO
from schemas.summary import RegenerateRequest, StatusUpdate, SummaryUpdate
from services.summary_service import SummaryService

from .deps import get_summary_service

router = APIRouter(prefix="/v2", tags=["summaries"])


def parse_date(date_str: str | None, end_of_day: bool = False) -> datetime | None:
    """
    날짜 문자열을 datetime으로 파싱

    Args:
        date_str: YYYY-MM-DD 형식의 날짜 문자열
        end_of_day: True이면 23:59:59로 설정

    Returns:
        datetime 객체 또는 None

    Raises:
        HTTPException: 날짜 형식이 잘못된 경우 400 에러
    """
    if not date_str:
        return None

    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        if end_of_day:
            dt = dt.replace(hour=23, minute=59, second=59)
        return dt
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format: '{date_str}'. Expected YYYY-MM-DD format.",
        ) from e


@router.get("/summaries")
async def api_summaries(
    status: str | None = Query(None, description="상태 필터"),
    region: str | None = Query(None, description="지역 필터"),
    keyword: str | None = Query(None, description="키워드/업체명 검색"),
    min_rating: float | None = Query(None, description="최소 평점"),
    max_rating: float | None = Query(None, description="최대 평점"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("branch_id"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    review_date_from: str | None = Query(
        None, description="시작일 (YYYY-MM-DD) - 이 기간에 리뷰가 있는 업체만 표시"
    ),
    review_date_to: str | None = Query(
        None, description="종료일 (YYYY-MM-DD) - 이 기간에 리뷰가 있는 업체만 표시"
    ),
    service: SummaryService = Depends(get_summary_service),
) -> list[dict[str, Any]]:
    """
    통합 요약 목록 조회

    날짜 필터 사용 시:
    - review_date_from ~ review_date_to 기간에 리뷰가 있는 업체만 반환
    - 종료일은 해당일 23:59:59까지 포함
    """
    parsed_date_from = parse_date(review_date_from)
    parsed_date_to = parse_date(review_date_to, end_of_day=True)

    return await service.get_summaries(
        status=status,
        region=region,
        keyword=keyword,
        min_rating=min_rating,
        max_rating=max_rating,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        order=order,
        review_date_from=parsed_date_from,
        review_date_to=parsed_date_to,
    )


@router.get("/summaries/{branch_id}")
async def api_summary_detail(
    branch_id: int, service: SummaryService = Depends(get_summary_service)
) -> dict[str, Any]:
    """특정 지점 요약 상세"""
    summary = await service.get_summary(branch_id)
    if summary:
        return summary
    raise HTTPException(status_code=404, detail="Not found")


@router.put("/summaries/{branch_id}")
async def api_update_summary(
    branch_id: int,
    data: SummaryUpdate,
    service: SummaryService = Depends(get_summary_service),
) -> dict[str, Any]:
    """요약 수정"""
    update_data = data.model_dump(exclude_unset=True)
    result = await service.update_summary(branch_id, update_data)
    return {"success": True, "data": result}


@router.put("/summaries/{branch_id}/status")
async def api_update_status(
    branch_id: int,
    data: StatusUpdate,
    service: SummaryService = Depends(get_summary_service),
) -> dict[str, Any]:
    """요약 상태 변경"""
    result = await service.update_status(branch_id, data.status)
    return {"success": True, "data": result}


@router.post("/summaries/{branch_id}/regenerate")
async def api_regenerate_summary(
    branch_id: int,
    data: RegenerateRequest = None,
    service: SummaryService = Depends(get_summary_service),
) -> dict[str, Any]:
    """AI 요약 재생성 (pending에 저장, 바로 적용 안 됨)"""
    period = data.period if data else "all"

    try:
        summary = await service.regenerate_summary(branch_id, period)
        return {"success": True, "summary": summary, "period": period, "pending": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/summaries/{branch_id}/apply-pending")
async def api_apply_pending_summary(
    branch_id: int,
    data: RegenerateRequest = None,
    service: SummaryService = Depends(get_summary_service),
) -> dict[str, Any]:
    """대기 중인 요약 적용 (pending → main)"""
    period = data.period if data else "all"

    try:
        result = await service.apply_pending_summary(branch_id, period)
        return {"success": True, **result.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/summaries/{branch_id}/discard-pending")
async def api_discard_pending_summary(
    branch_id: int,
    data: RegenerateRequest = None,
    service: SummaryService = Depends(get_summary_service),
) -> dict[str, Any]:
    """대기 중인 요약 취소 (삭제)"""
    period = data.period if data else "all"

    try:
        result = await service.discard_pending_summary(branch_id, period)
        return {"success": True, **result.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


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
    service: SummaryService = Depends(get_summary_service),
) -> dict[str, Any]:
    """요약 통계"""
    result = await service.get_stats()
    return result.to_dict()


@router.get("/stats/region")
async def api_region_stats(
    service: SummaryService = Depends(get_summary_service),
) -> list[dict[str, Any]]:
    """지역별 통계"""
    result = await service.get_region_stats()
    return [r.to_dict() for r in result]


@router.get("/stats/rating")
async def api_rating_stats(
    service: SummaryService = Depends(get_summary_service),
) -> dict[str, Any]:
    """평점 분포 통계"""
    result = await service.get_rating_stats()
    return result.to_dict()


@router.get("/summaries/{branch_id}/reviews")
async def api_branch_reviews(
    branch_id: int,
    car_model: str | None = Query(None, description="차량 모델 필터"),
    sentiment: str | None = Query(None, description="감정 필터"),
    review_date_from: str | None = Query(
        None, description="시작일 (YYYY-MM-DD) - 이 날짜 이후 리뷰만 조회"
    ),
    review_date_to: str | None = Query(
        None, description="종료일 (YYYY-MM-DD) - 이 날짜 이전 리뷰만 조회"
    ),
    limit: int = Query(100, ge=1, le=500, description="조회 개수"),
    offset: int = Query(0, ge=0, description="오프셋"),
    service: SummaryService = Depends(get_summary_service),
) -> dict[str, Any]:
    """
    지점별 리뷰 목록 조회 (필터링 지원)

    branch_reviews 테이블에서 원본 리뷰를 조회합니다.

    필터 옵션:
    - car_model: 차량 모델
    - sentiment: 감정 (positive, neutral, negative)
    - review_date_from ~ review_date_to: 날짜 범위 (종료일은 23:59:59까지 포함)
    """
    parsed_date_from = parse_date(review_date_from)
    parsed_date_to = parse_date(review_date_to, end_of_day=True)

    result = await service.get_branch_reviews(
        branch_id=branch_id,
        car_model=car_model,
        sentiment=sentiment,
        review_date_from=parsed_date_from,
        review_date_to=parsed_date_to,
        limit=limit,
        offset=offset,
    )
    return result.to_dict()


@router.get("/summaries/{branch_id}/detail")
async def api_branch_detail(
    branch_id: int,
    include_summaries: bool = Query(True, description="기간별 요약 포함 여부"),
    max_reviews: int = Query(500, ge=1, le=1000, description="최대 리뷰 수"),
    service: SummaryService = Depends(get_summary_service),
) -> dict[str, Any]:
    """
    지점 상세 분석 (JSON)

    - 리뷰별 키워드 추출
    - 태그+감정 분류
    - 기간별 요약
    """
    result = await service.get_branch_detail(
        branch_id=branch_id,
        include_summaries=include_summaries,
        max_reviews=max_reviews,
    )
    if result:
        return result.to_dict()
    raise HTTPException(status_code=404, detail="Not found")


@router.get("/summaries/{branch_id}/car-models")
async def api_car_model_tags(
    branch_id: int,
    car_model: str | None = Query(None, description="특정 차량 모델만 조회"),
    service: SummaryService = Depends(get_summary_service),
) -> BranchCarModelsDTO:
    """
    지점별 차량 모델 태그 분석

    각 차량 모델별로 태그와 감정 통계를 반환합니다.

    응답 예시:
    ```json
    {
      "branch_id": 1234,
      "car_models": [
        {
          "name": "아반떼",
          "review_count": 50,
          "tags": [
            {"name": "차량청결", "positive": 40, "negative": 5, "total": 45},
            {"name": "가성비", "positive": 35, "negative": 3, "total": 38}
          ]
        }
      ]
    }
    ```
    """
    return await service.get_car_model_tags(
        branch_id=branch_id,
        car_model=car_model,
    )
