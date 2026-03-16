"""프롬프트 프리셋 서비스"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import HTTPException, status

if TYPE_CHECKING:
    from repository.report_repository import PresetRepository

logger = logging.getLogger(__name__)


class PresetService:
    """프리셋 CRUD 비즈니스 로직"""

    def __init__(self, preset_repo: PresetRepository):
        self.preset_repo = preset_repo

    async def list_presets(self, branch_type: str | None = None) -> list[dict]:
        """프리셋 목록 조회"""
        return await self.preset_repo.get_all_active(branch_type)

    async def get_preset(self, preset_id: int) -> dict:
        """프리셋 단일 조회"""
        preset = await self.preset_repo.get_by_id(preset_id)
        if not preset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"프리셋을 찾을 수 없습니다 (id={preset_id})",
            )
        return preset

    async def create_preset(self, data: dict) -> dict:
        """프리셋 생성"""
        result = await self.preset_repo.create(data)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="프리셋 생성 실패",
            )
        return result

    async def update_preset(self, preset_id: int, data: dict) -> dict:
        """프리셋 수정"""
        existing = await self.preset_repo.get_by_id(preset_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"프리셋을 찾을 수 없습니다 (id={preset_id})",
            )
        result = await self.preset_repo.update_preset(preset_id, data)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="프리셋 수정 실패",
            )
        return result

    async def delete_preset(self, preset_id: int) -> bool:
        """프리셋 삭제"""
        existing = await self.preset_repo.get_by_id(preset_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"프리셋을 찾을 수 없습니다 (id={preset_id})",
            )
        return await self.preset_repo.delete_preset(preset_id)
