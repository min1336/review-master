"""
통합 요약 API (FastAPI)

Router: /api/summaries
담당: HTTP 요청/응답 처리만 (비즈니스 로직은 Service에서)

주요 엔드포인트:
- GET /summaries: 업체 목록 조회 (날짜 필터링 지원)
- PATCH /summaries/{branch_id}: 요약 부분 수정
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from schemas.common import ApiListResponseModel, ApiResponseModel, api_list_response, api_response, parse_date
from schemas.dto import BranchCarModelsDTO, BranchReviewsDTO, PendingSummaryResultDTO, RegionStatsDTO, SummaryStatsDTO
from models.summary import Summary
from schemas.query import RegenerateRequest, SummaryUpdate
from services.summary_service import SummaryService

from .deps import get_summary_service

router = APIRouter(tags=["summaries"])


@router.get("", response_model=ApiListResponseModel[Summary])
async def api_summaries(
    region: str | None = Query(None, description="지역 필터 (텍스트 매칭)"),
    region_group: str | None = Query(None, description="지역 그룹 필터 (서울/경기도/강원도/충청도/전라도/경상도/제주도/해외)"),
    keyword: str | None = Query(None, description="키워드/업체명 검색"),
    min_rating: float | None = Query(None, description="최소 평점"),
    max_rating: float | None = Query(None, description="최대 평점"),
    min_reviews: int = Query(0, ge=0, description="최소 리뷰 수"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("branch_id"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    # NOTE: str | None 유지 — parse_date()가 end_of_day 처리(23:59:59)를 수행하므로
    # FastAPI 내장 date 타입으로 변경 시 end_of_day 로직이 누락됨
    review_date_from: str | None = Query(
        None, description="시작일 (YYYY-MM-DD) - 이 기간에 리뷰가 있는 업체만 표시"
    ),
    review_date_to: str | None = Query(
        None, description="종료일 (YYYY-MM-DD) - 이 기간에 리뷰가 있는 업체만 표시"
    ),
    service: SummaryService = Depends(get_summary_service),
) -> dict[str, Any]:
    """
    통합 요약 목록 조회

    날짜 필터 사용 시:
    - review_date_from ~ review_date_to 기간에 리뷰가 있는 업체만 반환
    - 종료일은 해당일 23:59:59까지 포함
    """
    parsed_date_from = parse_date(review_date_from)
    parsed_date_to = parse_date(review_date_to, end_of_day=True)

    summaries = await service.get_summaries(
        region=region,
        region_group=region_group,
        keyword=keyword,
        min_rating=min_rating,
        max_rating=max_rating,
        min_reviews=min_reviews,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        order=order,
        review_date_from=parsed_date_from,
        review_date_to=parsed_date_to,
    )
    return api_list_response(summaries)


@router.get("/stats", response_model=ApiResponseModel[SummaryStatsDTO])
async def api_stats(
    service: SummaryService = Depends(get_summary_service),
) -> dict[str, Any]:
    """요약 통계"""
    result = await service.get_stats()
    return api_response(result.model_dump(by_alias=True))


@router.get("/stats/region", response_model=ApiListResponseModel[RegionStatsDTO])
async def api_region_stats(
    service: SummaryService = Depends(get_summary_service),
) -> dict[str, Any]:
    """지역별 통계"""
    result = await service.get_region_stats()
    return api_list_response([r.model_dump(by_alias=True) for r in result])


# ================================================================
# Path parameter 경로 (/{branch_id}/*)
# ================================================================


@router.get("/{branch_id}", response_model=ApiResponseModel[dict])
async def api_summary_detail(
    branch_id: int, service: SummaryService = Depends(get_summary_service)
) -> dict[str, Any]:
    """특정 지점 요약 상세"""
    summary = await service.get_summary(branch_id)
    if summary:
        return api_response(summary)
    raise HTTPException(status_code=404, detail="Not found")


@router.get("/{branch_id}/text", response_model=ApiResponseModel[dict])
async def api_summary_text(
    branch_id: int,
    service: SummaryService = Depends(get_summary_service),
) -> dict[str, Any]:
    """외부 제공용 — 요약 텍스트만 반환"""
    summary = await service.get_summary_by_branch_id(branch_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Not found")
    text = SummaryService.pick_latest_summary(summary)
    return api_response({"summary": text or "요약이 아직 생성되지 않았습니다."})


@router.patch("/{branch_id}", response_model=ApiResponseModel[dict])
async def api_update_summary(
    branch_id: int,
    data: SummaryUpdate,
    service: SummaryService = Depends(get_summary_service),
) -> dict[str, Any]:
    """요약 부분 수정 (필드, 상태 포함)"""
    update_data = data.model_dump(exclude_unset=True)
    result = await service.update_summary(branch_id, update_data)
    return api_response(result)


@router.post("/{branch_id}/apply-pending", response_model=ApiResponseModel[PendingSummaryResultDTO])
async def api_apply_pending_summary(
    branch_id: int,
    data: RegenerateRequest | None = Body(None),
    service: SummaryService = Depends(get_summary_service),
) -> dict[str, Any]:
    """대기 중인 요약 적용 (pending -> main)"""
    period = data.period if data else "all"

    try:
        result = await service.apply_pending_summary(branch_id, period)
        return api_response(result.model_dump(by_alias=True))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{branch_id}/discard-pending", response_model=ApiResponseModel[PendingSummaryResultDTO])
async def api_discard_pending_summary(
    branch_id: int,
    data: RegenerateRequest | None = Body(None),
    service: SummaryService = Depends(get_summary_service),
) -> dict[str, Any]:
    """대기 중인 요약 취소 (삭제)"""
    period = data.period if data else "all"

    try:
        result = await service.discard_pending_summary(branch_id, period)
        return api_response(result.model_dump(by_alias=True))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{branch_id}/regenerate", response_model=ApiResponseModel[dict])
async def api_regenerate_summary(
    branch_id: int,
    pending: bool = Query(True, description="True=승인 대기, False=즉시 적용"),
    service: SummaryService = Depends(get_summary_service),
) -> dict[str, Any]:
    """
    AI 요약 재생성 (태그+감정+리뷰 데이터 활용)

    기간 자동 선택:
    - 1개월 리뷰 >= 30개 -> 1개월 요약
    - 1개월 리뷰 < 30개 -> 3개월로 확장
    - 3개월 리뷰 < 30개 -> 6개월로 확장
    - 6개월 리뷰 < 30개 -> 1년으로 확장
    - 1년 리뷰 < 30개 -> 리뷰 부족 메시지

    pending=true: pending_summaries에 저장 (대시보드 승인 대기)
    pending=false: 즉시 적용 (n8n 등 외부 호출용)
    """
    try:
        if pending:
            result = await service.generate_pending_summary(branch_id)
        else:
            result = await service.generate_summary_with_data(branch_id)
        return api_response(result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{branch_id}/reviews", response_model=ApiResponseModel[BranchReviewsDTO])
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
    return api_response(result.model_dump(by_alias=True))


@router.get("/{branch_id}/car-models", response_model=ApiResponseModel[BranchCarModelsDTO])
async def api_car_model_tags(
    branch_id: int,
    car_model: str | None = Query(None, description="특정 차량 모델만 조회"),
    service: SummaryService = Depends(get_summary_service),
) -> dict[str, Any]:
    """
    지점별 차량 모델 태그 분석

    각 차량 모델별로 태그와 감정 통계를 반환합니다.
    """
    result = await service.get_car_model_tags(
        branch_id=branch_id,
        car_model=car_model,
    )
    return api_response(result.model_dump(by_alias=True))
