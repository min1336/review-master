"""동기화 메타데이터 Repository"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from core.timezone import utc_now

from repository.session import execute_with_retry
from supabase import AsyncClient

logger = logging.getLogger(__name__)

# 락 타임아웃 (분) - 이 시간 이상 락이 걸려있으면 강제 해제
LOCK_TIMEOUT_MINUTES = 30


class SyncMetadataRepository:
    """동기화 메타데이터 관리 (last_sync_at, is_running 등)"""

    TABLE_NAME = "sync_metadata"

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def get_last_sync_at(self, sync_type: str = "new_review") -> datetime | None:
        """마지막 동기화 시간 조회"""
        try:
            query = (
                self._client.table(self.TABLE_NAME)
                .select("last_sync_at")
                .eq("sync_type", sync_type)
                .single()
            )
            result = await execute_with_retry(query)
            if result.data and result.data.get("last_sync_at"):
                return datetime.fromisoformat(result.data["last_sync_at"].replace("Z", "+00:00"))
            return None
        except Exception as e:
            logger.debug(f"No sync metadata found for {sync_type}: {e}")
            return None

    async def update_last_sync_at(
        self, sync_type: str = "new_review", sync_at: datetime | None = None
    ) -> bool:
        """마지막 동기화 시간 업데이트"""
        try:
            sync_at = sync_at or utc_now()
            query = (
                self._client.table(self.TABLE_NAME)
                .upsert({
                    "sync_type": sync_type,
                    "last_sync_at": sync_at.isoformat(),
                    "updated_at": utc_now().isoformat(),
                }, on_conflict="sync_type")
            )
            await execute_with_retry(query)
            return True
        except Exception as e:
            logger.error(f"Failed to update last_sync_at: {e}")
            return False

    async def acquire_lock(self, sync_type: str = "new_review") -> bool:
        """
        동기화 락 획득 (동시 실행 방지)

        - 30분 이상 락이 걸려있으면 강제 해제 후 획득
        """
        try:
            now = utc_now()

            # 1. 타임아웃된 락 강제 해제 (30분 이상)
            await self._release_stale_lock(sync_type)

            # 2. is_running=false인 경우에만 true로 업데이트
            query = (
                self._client.table(self.TABLE_NAME)
                .update({"is_running": True, "lock_acquired_at": now.isoformat()})
                .eq("sync_type", sync_type)
                .eq("is_running", False)
            )
            result = await execute_with_retry(query)

            # 업데이트된 행이 있으면 락 획득 성공
            if result.data and len(result.data) > 0:
                return True

            # 3. 행이 없으면 새로 생성 시도
            try:
                insert_query = (
                    self._client.table(self.TABLE_NAME)
                    .insert({
                        "sync_type": sync_type,
                        "is_running": True,
                        "lock_acquired_at": now.isoformat(),
                    })
                )
                await execute_with_retry(insert_query)
                return True
            except Exception:
                # 이미 존재하고 is_running=true인 경우
                return False

        except Exception as e:
            logger.error(f"Failed to acquire lock: {e}")
            return False

    async def _release_stale_lock(self, sync_type: str) -> None:
        """타임아웃된 락 강제 해제 (30분 이상)"""
        try:
            timeout_threshold = utc_now() - timedelta(minutes=LOCK_TIMEOUT_MINUTES)

            query = (
                self._client.table(self.TABLE_NAME)
                .update({"is_running": False, "lock_acquired_at": None})
                .eq("sync_type", sync_type)
                .eq("is_running", True)
                .lt("lock_acquired_at", timeout_threshold.isoformat())
            )
            result = await execute_with_retry(query)

            if result.data and len(result.data) > 0:
                logger.warning(f"Stale lock released for {sync_type} (timeout: {LOCK_TIMEOUT_MINUTES}min)")
        except Exception as e:
            logger.debug(f"Failed to release stale lock: {e}")

    async def release_lock(self, sync_type: str = "new_review") -> bool:
        """동기화 락 해제"""
        try:
            query = (
                self._client.table(self.TABLE_NAME)
                .update({"is_running": False, "lock_acquired_at": None})
                .eq("sync_type", sync_type)
            )
            await execute_with_retry(query)
            return True
        except Exception as e:
            logger.error(f"Failed to release lock: {e}")
            return False

    async def is_running(self, sync_type: str = "new_review") -> bool:
        """동기화 실행 중인지 확인"""
        try:
            query = (
                self._client.table(self.TABLE_NAME)
                .select("is_running")
                .eq("sync_type", sync_type)
                .single()
            )
            result = await execute_with_retry(query)
            return result.data.get("is_running", False) if result.data else False
        except Exception:
            return False
