"""리뷰 동기화 서비스 - RealtimePipeline 통합"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from domain.pipeline.realtime_pipeline import RealtimePipeline
from infrastructure.athena import AthenaClient
from repository.review_repository import BranchReviewRepository
from repository.sync_metadata_repository import SyncMetadataRepository
from repository.session import get_client
from schemas.sync import SyncResultResponse, SyncStatusResponse

logger = logging.getLogger(__name__)

SYNC_TYPE = "daily_pipeline"


class SyncService:
    """리뷰 동기화 서비스 - 태그/감정 분석 포함"""

    def __init__(
        self,
        review_repo: BranchReviewRepository,
        athena_client: AthenaClient | None = None,
    ) -> None:
        self._review_repo = review_repo
        self._athena_client = athena_client
        self._pipeline = RealtimePipeline()

    async def get_athena_sync_status(self) -> SyncStatusResponse:
        """동기화 상태 조회"""
        client = await get_client()
        metadata_repo = SyncMetadataRepository(client)

        # 마지막 동기화 시간 조회
        last_sync_at = await metadata_repo.get_last_sync_at(SYNC_TYPE)

        # 신규 리뷰 수 조회
        new_reviews = await self._review_repo.get_new_review_count()

        return SyncStatusResponse(
            last_sync_at=last_sync_at,
            total_reviews=0,
            new_reviews=new_reviews,
        )

    async def sync_reviews(self) -> SyncResultResponse:
        """
        Athena에서 리뷰 조회 + RealtimePipeline 실행 (가공 데이터만 저장)

        1. last_sync_at 이후 리뷰 조회
        2. 각 리뷰에 RealtimePipeline 실행
        3. 가공 데이터 저장 (branch_sentiment_stats, branch_tags)
        4. last_sync_at 업데이트

        ※ 리뷰 원본은 저장하지 않음 (10분 스케줄러가 담당)
        """
        start_time = datetime.now()

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
                last_sync_at = datetime.now() - timedelta(days=7)

            logger.info(f"파이프라인 시작: {last_sync_at} 이후 리뷰 분석")
            print(f"[DailyPipeline] 시작: {last_sync_at} 이후 리뷰 분석")

            # 2. Athena에서 리뷰 조회
            athena_reviews = self._athena_client.fetch_reviews_since(last_sync_at)

            if not athena_reviews:
                # 동기화 시간만 업데이트
                await metadata_repo.update_last_sync_at(SYNC_TYPE)
                return SyncResultResponse(
                    success=True,
                    message="분석할 신규 리뷰가 없습니다",
                    synced_count=0,
                    new_reviews=0,
                    duration_seconds=(datetime.now() - start_time).total_seconds(),
                )

            print(f"[DailyPipeline] Athena 조회 완료: {len(athena_reviews)}개")

            # 3. 중복 제거
            seen_ids = set()
            reviews_to_process = []
            for row in athena_reviews:
                review_id = row.get("review_id")
                if review_id in seen_ids:
                    continue
                seen_ids.add(review_id)
                reviews_to_process.append(row)

            # 4. 각 리뷰에 RealtimePipeline 실행 (가공 데이터 저장)
            processed_count = 0
            failed_count = 0

            for i, row in enumerate(reviews_to_process):
                try:
                    # RealtimePipeline: 감정/태그 분석 + DB 저장
                    # → branch_sentiment_stats 증분 업데이트
                    # → branch_tags 증분 업데이트
                    pipeline_result = await self._pipeline.process({
                        "branch_id": row.get("branch_id"),
                        "content": row.get("content"),
                        "rating_service": self._parse_float(row.get("rating_service")),
                        "rating_car": self._parse_float(row.get("rating_car")),
                        "rating_convenience": self._parse_float(row.get("rating_convenience")),
                    })

                    if pipeline_result.saved:
                        processed_count += 1
                    else:
                        failed_count += 1

                    # 진행 로그 (100개마다)
                    if (i + 1) % 100 == 0:
                        print(f"[DailyPipeline] 진행: {i + 1}/{len(reviews_to_process)}")

                except Exception as e:
                    logger.warning(f"리뷰 처리 실패 (review_id={row.get('review_id')}): {e}")
                    failed_count += 1

            # 5. last_sync_at 업데이트
            await metadata_repo.update_last_sync_at(SYNC_TYPE)

            duration = (datetime.now() - start_time).total_seconds()

            logger.info(
                f"파이프라인 완료: {processed_count}개 분석, {failed_count}개 실패 ({duration:.1f}초)"
            )
            print(
                f"[DailyPipeline] 완료: {processed_count}개 분석, {failed_count}개 실패 ({duration:.1f}초)"
            )

            return SyncResultResponse(
                success=True,
                message=f"{processed_count}개 리뷰 분석 완료 (태그/감정 통계 업데이트)",
                synced_count=processed_count,
                new_reviews=0,  # 리뷰 원본은 저장하지 않음
                duration_seconds=duration,
            )

        except Exception as e:
            logger.error(f"파이프라인 실패: {e}")
            return SyncResultResponse(
                success=False,
                message="파이프라인 실행 중 오류가 발생했습니다",
                error=str(e),
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

    async def mark_reviews_as_read(
        self, review_ids: list[int] | None = None
    ) -> int:
        """리뷰 읽음 처리"""
        return await self._review_repo.mark_reviews_as_read(review_ids)

    def _parse_float(self, value: str | None) -> float | None:
        """문자열을 float로 변환"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
