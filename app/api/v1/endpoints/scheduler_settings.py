"""스케줄러 설정 API 엔드포인트"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.scheduler_settings_service import SchedulerSettingsDTO, SchedulerSettingsService

from .deps import get_scheduler_settings_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["scheduler-settings"])


class UpdateSettingsRequest(BaseModel):
    """설정 업데이트 요청"""

    summary_cycle: Literal["weekly", "biweekly", "monthly"] | None = Field(
        None, description="요약 주기"
    )
    min_reviews: int | None = Field(None, ge=10, le=200, description="최소 리뷰 수")
    auto_approve: bool | None = Field(None, description="자동 승인 여부")


class SettingsResponse(BaseModel):
    """설정 응답"""

    success: bool
    data: SchedulerSettingsDTO | None = None
    message: str | None = None


@router.get("/{branch_id}", response_model=SettingsResponse)
async def get_scheduler_settings(
    branch_id: int,
    service: SchedulerSettingsService = Depends(get_scheduler_settings_service),
) -> SettingsResponse:
    """
    업체별 스케줄러 설정 조회

    - 설정이 없으면 기본값 반환
    """
    settings = await service.get_settings(branch_id)

    if not settings:
        # 기본 설정 생성
        settings = await service.create_default_settings(branch_id)

    return SettingsResponse(
        success=True,
        data=settings,
    )


@router.put("/{branch_id}", response_model=SettingsResponse)
async def update_scheduler_settings(
    branch_id: int,
    request: UpdateSettingsRequest,
    service: SchedulerSettingsService = Depends(get_scheduler_settings_service),
) -> SettingsResponse:
    """
    업체별 스케줄러 설정 수정

    - summary_cycle: 요약 주기 (weekly/biweekly/monthly)
    - min_reviews: 최소 리뷰 수 (10~200)
    - auto_approve: 자동 승인 여부
    """
    settings = await service.update_settings(
        branch_id=branch_id,
        summary_cycle=request.summary_cycle,
        min_reviews=request.min_reviews,
        auto_approve=request.auto_approve,
    )

    if not settings:
        raise HTTPException(status_code=500, detail="설정 저장 실패")

    return SettingsResponse(
        success=True,
        data=settings,
        message="설정이 저장되었습니다.",
    )


@router.post("/{branch_id}/reset", response_model=SettingsResponse)
async def reset_scheduler_settings(
    branch_id: int,
    service: SchedulerSettingsService = Depends(get_scheduler_settings_service),
) -> SettingsResponse:
    """설정 초기화 (기본값으로)"""
    settings = await service.create_default_settings(branch_id)

    if not settings:
        raise HTTPException(status_code=500, detail="설정 초기화 실패")

    return SettingsResponse(
        success=True,
        data=settings,
        message="설정이 초기화되었습니다.",
    )
