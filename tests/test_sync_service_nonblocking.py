"""SyncService.sync_reviews()가 이벤트 루프를 블로킹하지 않는지 검증하는 회귀 테스트.

원인: sync_service.py에서 AthenaClient.fetch_reviews_since()를
asyncio.to_thread() 없이 직접 호출하면 time.sleep() 폴링 루프가
이벤트 루프를 블로킹하여 502 Gateway Timeout이 발생함.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.sync_service import SyncService

# Athena 호출 진행 중인지 추적하는 플래그
_athena_in_progress = False


def _blocking_fetch(since, until=None):
    """동기 블로킹을 시뮬레이션하는 fake fetch_reviews_since.

    실제 AthenaClient._execute_query()는 time.sleep(2) 폴링 루프를 사용하므로
    이것은 축소된 시뮬레이션이다.
    """
    global _athena_in_progress
    _athena_in_progress = True
    time.sleep(0.5)
    _athena_in_progress = False
    return [
        {
            "review_id": "1001",
            "reservation_id": "R1",
            "company_id": "C1",
            "branch_id": "B1",
            "company_name": "테스트업체",
            "branch_name": "테스트지점",
            "rating_service": "5",
            "rating_car": "5",
            "rating_convenience": "5",
            "content": "좋아요",
            "review_date": "2026-01-01",
            "status": "1",
        }
    ]


@pytest.mark.asyncio
async def test_sync_reviews_does_not_block_event_loop():
    """sync_reviews() 실행 중 이벤트 루프가 블로킹되지 않아야 한다.

    asyncio.to_thread()로 감싸지 않으면 time.sleep()이 이벤트 루프를
    블로킹하여 동시 코루틴이 실행되지 못한다.

    검증 방식:
    - Athena 호출이 '진행 중'인 동안에만 heartbeat를 카운트한다.
    - to_thread 사용 시: 이벤트 루프가 자유로우므로 heartbeat가 실행됨.
    - 직접 호출 시: time.sleep()이 이벤트 루프를 점유하므로 heartbeat 0회.
    """
    global _athena_in_progress
    _athena_in_progress = False

    # --- Arrange ---
    mock_athena = MagicMock()
    mock_athena.fetch_reviews_since = _blocking_fetch

    mock_review_repo = AsyncMock()
    mock_review_repo.count_existing_review_ids = AsyncMock(return_value=0)
    mock_review_repo.upsert_batch = AsyncMock(return_value=1)
    mock_review_repo.commit = AsyncMock()

    mock_pipeline = AsyncMock()
    mock_pipeline.run = AsyncMock(
        return_value=MagicMock(processed_reviews=1)
    )

    service = SyncService(
        review_repo=mock_review_repo,
        athena_client=mock_athena,
        pipeline=mock_pipeline,
    )

    # Athena 호출 **진행 중**에만 카운트되는 heartbeat
    heartbeat_during_athena = 0

    async def heartbeat():
        nonlocal heartbeat_during_athena
        for _ in range(20):
            await asyncio.sleep(0.05)
            if _athena_in_progress:
                heartbeat_during_athena += 1

    # --- Act ---
    mock_session = AsyncMock()
    mock_metadata_repo = AsyncMock()
    mock_metadata_repo.get_last_sync_at = AsyncMock(return_value=None)
    mock_metadata_repo.update_last_sync_at = AsyncMock()

    with (
        patch("services.sync_service.get_session_factory") as mock_sf,
        patch(
            "services.sync_service.SyncMetadataRepository",
            return_value=mock_metadata_repo,
        ),
    ):
        mock_sf.return_value = MagicMock(return_value=mock_session)

        await asyncio.gather(
            service.sync_reviews(date_from="2026-03-03", date_to="2026-03-03"),
            heartbeat(),
        )

    # --- Assert ---
    # to_thread()를 사용하면 0.5초 블로킹 동안 heartbeat가 ~8회 실행됨.
    # 직접 호출이면 이벤트 루프가 점유되어 heartbeat_during_athena == 0.
    assert heartbeat_during_athena >= 2, (
        f"이벤트 루프가 Athena 호출 중 블로킹됨: "
        f"heartbeat가 Athena 진행 중 {heartbeat_during_athena}회 실행됨 "
        f"(최소 2회 이상이어야 함). "
        f"AthenaClient 호출이 asyncio.to_thread()로 감싸져 있는지 확인하세요."
    )
