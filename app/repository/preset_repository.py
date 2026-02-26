"""프롬프트 프리셋 Repository"""

from __future__ import annotations

import logging

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from repository.orm_models import PromptPresetORM

logger = logging.getLogger(__name__)


class PresetRepository:
    """프롬프트 프리셋 CRUD Repository"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_all_active(self, branch_type: str | None = None) -> list[dict]:
        """활성 프리셋 목록 (전역 + 지점유형별 필터)"""
        try:
            stmt = (
                select(PromptPresetORM)
                .where(PromptPresetORM.is_active.is_(True))
                .order_by(PromptPresetORM.display_order, PromptPresetORM.created_at)
            )
            result = await self._session.execute(stmt)
            rows = result.scalars().all()

            # 전역(branch_type=None) + 매칭 branch_type 필터
            return [
                self._to_dict(row) for row in rows
                if row.branch_type is None
                or row.branch_type == branch_type
            ]
        except Exception as e:
            logger.error(f"프리셋 목록 조회 실패: {e}")
            return []

    async def get_by_id(self, preset_id: int) -> dict | None:
        """프리셋 단일 조회"""
        try:
            stmt = select(PromptPresetORM).where(PromptPresetORM.id == preset_id)
            result = await self._session.execute(stmt)
            row = result.scalar_one_or_none()
            return self._to_dict(row) if row else None
        except Exception:
            return None

    async def create(self, data: dict) -> dict | None:
        """프리셋 생성"""
        try:
            preset = PromptPresetORM(**data)
            self._session.add(preset)
            await self._session.flush()
            await self._session.refresh(preset)
            return self._to_dict(preset)
        except Exception as e:
            logger.error(f"프리셋 생성 실패: {e}")
            raise

    async def update(self, preset_id: int, data: dict) -> dict | None:
        """프리셋 수정"""
        try:
            from core.timezone import utc_now
            data["updated_at"] = utc_now()
            stmt = (
                update(PromptPresetORM)
                .where(PromptPresetORM.id == preset_id)
                .values(**data)
            )
            await self._session.execute(stmt)
            await self._session.flush()
            # 업데이트된 행 조회
            row = await self._session.get(PromptPresetORM, preset_id)
            return self._to_dict(row) if row else None
        except Exception as e:
            logger.error(f"프리셋 수정 실패: {e}")
            raise

    async def delete(self, preset_id: int) -> bool:
        """프리셋 삭제"""
        try:
            stmt = delete(PromptPresetORM).where(PromptPresetORM.id == preset_id)
            result = await self._session.execute(stmt)
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"프리셋 삭제 실패: {e}")
            return False

    @staticmethod
    def _to_dict(row: PromptPresetORM) -> dict:
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description or "",
            "branch_type": row.branch_type,
            "analysis_perspective": row.analysis_perspective,
            "tone": row.tone,
            "detail_level": row.detail_level,
            "focus_areas": row.focus_areas or [],
            "custom_instruction": row.custom_instruction or "",
            "temperature": row.temperature,
            "summary_max_length": row.summary_max_length,
            "eval_max_length": row.eval_max_length,
            "is_default": row.is_default,
            "is_active": row.is_active,
            "display_order": row.display_order,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
