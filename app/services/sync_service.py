"""리뷰 동기화 서비스 - UnifiedPipeline 통합"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from core.timezone import utc_now

from domain.pipeline.unified_pipeline import UnifiedPipeline
from infrastructure.athena import AthenaClient
from repository.review_repository import BranchReviewRepository
from repository.sync_metadata_repository import SyncMetadataRepository
from repository.session import get_client
from schemas.sync import SyncResultResponse

logger = logging.getLogger(__name__)

SYNC_TYPE = "daily_pipeline"


class SyncService:
    """리뷰 동기화 서비스 - 태그/감정 분석 포함"""

    def __init__(
        self,
        review_repo: BranchReviewRepository,
        athena_client: AthenaClient | None = None,
        pipeline: UnifiedPipeline | None = None,
    ) -> None:
        self._review_repo = review_repo
        self._athena_client = athena_client
        self._pipeline = pipeline or UnifiedPipeline()

    async def sync_reviews(
        self,
        progress_callback: Callable[[int, str], Awaitable[None]] | None = None,
    ) -> SyncResultResponse:
        """
        Athena에서 리뷰 조회 → branch_reviews 저장 → UnifiedPipeline 실행

        Args:
            progress_callback: 진행률 콜백 (progress%, message). None이면 무시.

        1. last_sync_at 이후 신규 리뷰 조회
        2. branch_reviews에 is_new=true로 원본 저장 (upsert)
        3. UnifiedPipeline 실행 (감정/태그 통계 저장)
        4. last_sync_at 업데이트
        """
        start_time = utc_now()

        if not self._athena_client:
            return SyncResultResponse(
                success=False,
                message="Athena 클라이언트가 설정되지 않았습니다",
                error="athena_client_not_configured",
            )

        try:
            client = await get_client()
            metadata_repo = SyncMetadataRepository(client)

            # 1. 마지막 동기화 시간 조회
            last_sync_at = await metadata_repo.get_last_sync_at(SYNC_TYPE)
            if not last_sync_at:
                last_sync_at = utc_now() - timedelta(days=7)

            logger.info(f"동기화 시작: {last_sync_at} 이후 리뷰 조회")
            print(f"[DailyPipeline] 시작: {last_sync_at} 이후 리뷰 조회")

            if progress_callback:
                await progress_callback(5, "동기화 시작")

            # 2. Athena에서 리뷰 조회
            athena_reviews = self._athena_client.fetch_reviews_since(last_sync_at)

            if not athena_reviews:
                await metadata_repo.update_last_sync_at(SYNC_TYPE)
                return SyncResultResponse(
                    success=True,
                    message="신규 리뷰가 없습니다",
                    synced_count=0,
                    new_reviews=0,
                    duration_seconds=(utc_now() - start_time).total_seconds(),
                )

            # 3. 중복 제거
            seen_ids: set[str] = set()
            reviews_to_process: list[dict] = []
            for row in athena_reviews:
                review_id = row.get("review_id")
                if review_id in seen_ids:
                    continue
                seen_ids.add(review_id)
                reviews_to_process.append(row)

            logger.info(f"Athena 조회 완료: {len(reviews_to_process)}개 (중복 제거 후)")

            if progress_callback:
                await progress_callback(20, f"Athena 조회 완료: {len(reviews_to_process)}건")

            # 4. branch_reviews에 원본 저장 (is_new=true)
            save_data = [
                {**row, "is_new": True} for row in reviews_to_process
            ]
            saved_count = await self._review_repo.upsert_batch(save_data)
            logger.info(f"branch_reviews 저장 완료: {saved_count}개 (is_new=true)")

            if progress_callback:
                await progress_callback(35, f"{saved_count}건 저장 완료")

            # 5. UnifiedPipeline 실행 (감정/태그 통계 저장)
            result = await self._pipeline.run(reviews_to_process, progress_callback)
            processed_count = result.processed_reviews
            failed_count = len(reviews_to_process) - result.processed_reviews

            # 6. last_sync_at 업데이트
            if progress_callback:
                await progress_callback(95, "메타데이터 업데이트")
            await metadata_repo.update_last_sync_at(SYNC_TYPE)

            duration = (utc_now() - start_time).total_seconds()

            logger.info(
                f"동기화 완료: {saved_count}개 저장, {processed_count}개 분석, "
                f"{failed_count}개 실패 ({duration:.1f}초)"
            )

            return SyncResultResponse(
                success=True,
                message=f"{saved_count}개 리뷰 저장 + {processed_count}개 분석 완료",
                synced_count=saved_count,
                new_reviews=saved_count,
                duration_seconds=duration,
            )

        except Exception as e:
            logger.error(f"동기화 실패: {e}")
            return SyncResultResponse(
                success=False,
                message="동기화 실행 중 오류가 발생했습니다",
                error=str(e),
                duration_seconds=(utc_now() - start_time).total_seconds(),
            )

    async def mark_reviews_as_read(
        self, review_ids: list[int] | None = None
    ) -> int:
        """리뷰 읽음 처리"""
        return await self._review_repo.mark_reviews_as_read(review_ids)
