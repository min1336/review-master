"""동기화 메타데이터 Repository"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.timezone import utc_now

from .orm_models import SyncMetadataORM

logger = logging.getLogger(__name__)

# 락 타임아웃 (분) - 이 시간 이상 락이 걸려있으면 강제 해제
LOCK_TIMEOUT_MINUTES = 30


class SyncMetadataRepository:
    """동기화 메타데이터 관리 (last_sync_at, is_running 등)"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_last_sync_at(self, sync_type: str = "new_review") -> datetime | None:
        """마지막 동기화 시간 조회"""
        try:
            result = await self._session.execute(
                select(SyncMetadataORM.last_sync_at)
                .where(SyncMetadataORM.sync_type == sync_type)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.debug("No sync metadata found for %s: %s", sync_type, e)
            return None

    async def update_last_sync_at(
        self, sync_type: str = "new_review", sync_at: datetime | None = None
    ) -> bool:
        """마지막 동기화 시간 업데이트"""
        try:
            sync_at = sync_at or utc_now()
            stmt = (
                pg_insert(SyncMetadataORM.__table__)
                .values(
                    sync_type=sync_type,
                    last_sync_at=sync_at,
                    updated_at=utc_now(),
                )
                .on_conflict_do_update(
                    index_elements=["sync_type"],
                    set_={
                        "last_sync_at": sync_at,
                        "updated_at": utc_now(),
                    },
                )
            )
            await self._session.execute(stmt)
            await self._session.flush()
            return True
        except Exception as e:
            logger.error("Failed to update last_sync_at: %s", e)
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
            stmt = (
                update(SyncMetadataORM)
                .where(SyncMetadataORM.sync_type == sync_type)
                .where(SyncMetadataORM.is_running == False)  # noqa: E712
                .values(is_running=True, lock_acquired_at=now)
            )
            result = await self._session.execute(stmt)
            await self._session.flush()

            # 업데이트된 행이 있으면 락 획득 성공
            if result.rowcount > 0:
                return True

            # 3. 행이 없으면 새로 생성 시도
            try:
                insert_stmt = (
                    pg_insert(SyncMetadataORM.__table__)
                    .values(
                        sync_type=sync_type,
                        is_running=True,
                        lock_acquired_at=now,
                    )
                )
                await self._session.execute(insert_stmt)
                await self._session.flush()
                return True
            except Exception:
                # 이미 존재하고 is_running=true인 경우
                return False

        except Exception as e:
            logger.error("Failed to acquire lock: %s", e)
            return False

    async def _release_stale_lock(self, sync_type: str) -> None:
        """타임아웃된 락 강제 해제 (30분 이상)"""
        try:
            timeout_threshold = utc_now() - timedelta(minutes=LOCK_TIMEOUT_MINUTES)

            stmt = (
                update(SyncMetadataORM)
                .where(SyncMetadataORM.sync_type == sync_type)
                .where(SyncMetadataORM.is_running == True)  # noqa: E712
                .where(SyncMetadataORM.lock_acquired_at < timeout_threshold)
                .values(is_running=False, lock_acquired_at=None)
            )
            result = await self._session.execute(stmt)
            await self._session.flush()

            if result.rowcount > 0:
                logger.warning(
                    f"Stale lock released for {sync_type} "
                    f"(timeout: {LOCK_TIMEOUT_MINUTES}min)"
                )
        except Exception as e:
            logger.debug("Failed to release stale lock: %s", e)

    async def release_lock(self, sync_type: str = "new_review") -> bool:
        """동기화 락 해제"""
        try:
            stmt = (
                update(SyncMetadataORM)
                .where(SyncMetadataORM.sync_type == sync_type)
                .values(is_running=False, lock_acquired_at=None)
            )
            await self._session.execute(stmt)
            await self._session.flush()
            return True
        except Exception as e:
            logger.error("Failed to release lock: %s", e)
            raise

    async def is_running(self, sync_type: str = "new_review") -> bool:
        """동기화 실행 중인지 확인"""
        try:
            result = await self._session.execute(
                select(SyncMetadataORM.is_running)
                .where(SyncMetadataORM.sync_type == sync_type)
            )
            value = result.scalar_one_or_none()
            return value if value is not None else False
        except Exception:
            return False
