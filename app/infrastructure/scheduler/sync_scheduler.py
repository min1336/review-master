"""리뷰 동기화 스케줄러"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from core.config import get_settings
from infrastructure.athena import AthenaClient
from repository.review_repository import BranchReviewRepository
from repository.session import get_client
from services.sync_service import SyncService

logger = logging.getLogger(__name__)


class SyncScheduler:
    """리뷰 동기화 스케줄러"""

    # 허용 간격 범위 (분)
    MIN_INTERVAL = 5
    MAX_INTERVAL = 30

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._settings = get_settings()
        self._is_running = False
        self._current_interval = self._settings.sync_interval_minutes

    async def start(self) -> None:
        """스케줄러 시작"""
        if not self._settings.scheduler_enabled:
            logger.info("스케줄러가 비활성화되어 있습니다 (SCHEDULER_ENABLED=false)")
            return

        if not self._settings.aws_access_key_id:
            logger.warning("AWS 자격증명이 설정되지 않아 스케줄러를 시작하지 않습니다")
            return

        # 동기화 작업 등록
        self._scheduler.add_job(
            self._sync_reviews_job,
            trigger=IntervalTrigger(minutes=self._current_interval),
            id="sync_reviews",
            name="Athena 리뷰 동기화",
            replace_existing=True,
            next_run_time=datetime.now(),  # 시작 시 즉시 1회 실행
        )

        self._scheduler.start()
        self._is_running = True

        logger.info(f"스케줄러 시작됨: {self._current_interval}분 간격으로 동기화")
        print(f"[Scheduler] 리뷰 동기화 스케줄러 시작 (간격: {self._current_interval}분)")

    async def stop(self) -> None:
        """스케줄러 종료"""
        if self._is_running:
            self._scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("스케줄러 종료됨")
            print("[Scheduler] 리뷰 동기화 스케줄러 종료")

    async def _sync_reviews_job(self) -> None:
        """리뷰 동기화 작업"""
        logger.info("스케줄러: 리뷰 동기화 작업 시작")
        print(f"[Scheduler] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 리뷰 동기화 시작")

        try:
            # 서비스 인스턴스 생성
            client = await get_client()
            review_repo = BranchReviewRepository(client)
            athena_client = AthenaClient()
            sync_service = SyncService(review_repo, athena_client)

            # 동기화 실행
            result = await sync_service.sync_reviews()

            if result.success:
                logger.info(
                    f"스케줄러: 동기화 완료 - {result.synced_count}개 리뷰 ({result.duration_seconds:.1f}초)"
                )
                print(
                    f"[Scheduler] 동기화 완료: {result.synced_count}개 리뷰 저장 ({result.duration_seconds:.1f}초)"
                )
            else:
                logger.error(f"스케줄러: 동기화 실패 - {result.error}")
                print(f"[Scheduler] 동기화 실패: {result.error}")

        except Exception as e:
            logger.error(f"스케줄러: 동기화 작업 중 오류 발생 - {e}")
            print(f"[Scheduler] 동기화 오류: {e}")

    @property
    def is_running(self) -> bool:
        """스케줄러 실행 상태"""
        return self._is_running

    def get_next_run_time(self) -> datetime | None:
        """다음 실행 시간 조회"""
        if not self._is_running:
            return None

        job = self._scheduler.get_job("sync_reviews")
        if job:
            return job.next_run_time
        return None

    def get_interval(self) -> int:
        """현재 동기화 간격 (분) 조회"""
        return self._current_interval

    async def update_interval(self, minutes: int) -> bool:
        """
        동기화 간격 변경

        Args:
            minutes: 새 간격 (5~30분)

        Returns:
            성공 여부
        """
        # 범위 검증
        if minutes < self.MIN_INTERVAL or minutes > self.MAX_INTERVAL:
            logger.warning(
                f"간격 범위 초과: {minutes}분 (허용: {self.MIN_INTERVAL}~{self.MAX_INTERVAL}분)"
            )
            return False

        self._current_interval = minutes
        logger.info(f"스케줄러 간격 변경: {minutes}분")
        print(f"[Scheduler] 동기화 간격 변경: {minutes}분")

        # 실행 중이면 작업 재등록
        if self._is_running:
            self._scheduler.reschedule_job(
                "sync_reviews",
                trigger=IntervalTrigger(minutes=minutes),
            )
            logger.info(f"스케줄러 작업 재등록됨: {minutes}분 간격")

        return True


# 싱글톤 인스턴스
_scheduler_instance: SyncScheduler | None = None


def get_scheduler() -> SyncScheduler:
    """스케줄러 싱글톤 인스턴스 반환"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = SyncScheduler()
    return _scheduler_instance
