"""
지점별 요약 부가 기능 API

Router: /api/summaries (summary_branch)
담당: AI 재생성, 리뷰 목록, 차량 모델 태그 분석
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from schemas.common import api_response, parse_date
from services.summary_service import SummaryService

from .deps import get_summary_service

router = APIRouter(tags=["summaries"])


@router.post("/{branch_id}/regenerate")
async def api_regenerate_summary(
    branch_id: int,
    mode: str = Query("marketing", pattern="^(marketing|operational)$"),
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

    생성된 요약은 pending_summaries에 저장됩니다 (승인 대기 상태).
    운영자가 '변경' 버튼으로 승인해야 실제 요약에 반영됩니다.
    """
    try:
        result = await service.generate_pending_summary(branch_id)
        return api_response(result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{branch_id}/reviews")
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
    return api_response(result.to_dict())


@router.get("/{branch_id}/car-models")
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
    return api_response(result.to_dict())
