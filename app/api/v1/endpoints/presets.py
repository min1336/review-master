"""프롬프트 프리셋 CRUD 엔드포인트"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from schemas.common import ApiResponseModel, api_list_response, api_response
from schemas.report import (
    PromptPresetCreate,
    PromptPresetUpdate,
)
from services.preset_service import PresetService

from .deps import get_preset_service

router = APIRouter(tags=["presets"])


@router.get("")
async def list_presets(
    branch_type: str | None = Query(None, pattern="^(airport|tourist|city)$"),
    service: PresetService = Depends(get_preset_service),
) -> dict[str, Any]:
    """프리셋 목록 조회"""
    presets = await service.list_presets(branch_type)
    return api_list_response(presets)


@router.get("/{preset_id}", response_model=ApiResponseModel[dict])
async def get_preset(
    preset_id: int,
    service: PresetService = Depends(get_preset_service),
) -> dict[str, Any]:
    """프리셋 상세 조회"""
    preset = await service.get_preset(preset_id)
    return api_response(preset)


@router.post("", response_model=ApiResponseModel[dict], status_code=201)
async def create_preset(
    body: PromptPresetCreate,
    service: PresetService = Depends(get_preset_service),
) -> dict[str, Any]:
    """프리셋 생성"""
    data = body.model_dump(exclude_none=True)
    preset = await service.create_preset(data)
    return api_response(preset)


@router.put("/{preset_id}", response_model=ApiResponseModel[dict])
async def update_preset(
    preset_id: int,
    body: PromptPresetUpdate,
    service: PresetService = Depends(get_preset_service),
) -> dict[str, Any]:
    """프리셋 수정"""
    data = body.model_dump(exclude_unset=True)
    preset = await service.update_preset(preset_id, data)
    return api_response(preset)


@router.delete("/{preset_id}")
async def delete_preset(
    preset_id: int,
    service: PresetService = Depends(get_preset_service),
) -> dict[str, Any]:
    """프리셋 삭제"""
    await service.delete_preset(preset_id)
    return {"success": True, "data": None}
