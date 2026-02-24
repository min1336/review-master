"""프롬프트 프리셋 Repository"""

from __future__ import annotations

import logging

from supabase._async.client import AsyncClient

logger = logging.getLogger(__name__)


class PresetRepository:
    """프롬프트 프리셋 CRUD Repository"""

    TABLE = "prompt_presets"

    def __init__(self, client: AsyncClient):
        self._client = client

    async def get_all_active(self, branch_type: str | None = None) -> list[dict]:
        """활성 프리셋 목록 (전역 + 지점유형별 필터)"""
        try:
            query = (
                self._client.table(self.TABLE)
                .select("*")
                .eq("is_active", True)
                .order("display_order")
                .order("created_at")
            )
            result = await query.execute()

            if not result.data:
                return []

            # 전역(branch_type=None) + 매칭 branch_type 필터
            return [
                row for row in result.data
                if row.get("branch_type") is None
                or row.get("branch_type") == branch_type
            ]
        except Exception as e:
            logger.error(f"프리셋 목록 조회 실패: {e}")
            return []

    async def get_by_id(self, preset_id: int) -> dict | None:
        """프리셋 단일 조회"""
        try:
            result = (
                await self._client.table(self.TABLE)
                .select("*")
                .eq("id", preset_id)
                .single()
                .execute()
            )
            return result.data if result.data else None
        except Exception:
            return None

    async def create(self, data: dict) -> dict | None:
        """프리셋 생성"""
        try:
            result = await self._client.table(self.TABLE).insert(data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"프리셋 생성 실패: {e}")
            raise

    async def update(self, preset_id: int, data: dict) -> dict | None:
        """프리셋 수정"""
        try:
            from core.timezone import utc_now
            data["updated_at"] = utc_now().isoformat()
            result = (
                await self._client.table(self.TABLE)
                .update(data)
                .eq("id", preset_id)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"프리셋 수정 실패: {e}")
            raise

    async def delete(self, preset_id: int) -> bool:
        """프리셋 삭제"""
        try:
            await (
                self._client.table(self.TABLE)
                .delete()
                .eq("id", preset_id)
                .execute()
            )
            return True
        except Exception as e:
            logger.error(f"프리셋 삭제 실패: {e}")
            return False
