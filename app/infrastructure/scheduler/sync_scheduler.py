"""리뷰 동기화 스케줄러"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from core.timezone import utc_now

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.config import get_settings
from domain.pipeline.steps.decay_job import DecayJob
from infrastructure.athena import AthenaClient
from repository.review_repository import BranchReviewRepository
from repository.session import get_client
from services.sync_service import SyncService

logger = logging.getLogger(__name__)


class SyncScheduler:
    """리뷰 동기화 스케줄러 - 매일 특정 시간에 실행"""

    # 기본 실행 시간 (오전 6시)
    DEFAULT_HOUR = 6
    DEFAULT_MINUTE = 0

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._settings = get_settings()
        self._is_running = False
        self._sync_hour = self._settings.sync_hour
        self._sync_minute = self._settings.sync_minute

    async def start(self) -> None:
        """스케줄러 시작"""
        if not self._settings.scheduler_enabled:
            logger.info("스케줄러가 비활성화되어 있습니다 (SCHEDULER_ENABLED=false)")
            return

        if not self._settings.aws_access_key_id:
            logger.warning("AWS 자격증명이 설정되지 않아 스케줄러를 시작하지 않습니다")
            return

        # 동기화 작업 등록 - 매일 특정 시간에 실행
        self._scheduler.add_job(
            self._sync_reviews_job,
            trigger=CronTrigger(hour=self._sync_hour, minute=self._sync_minute, timezone="Asia/Seoul"),
            id="sync_reviews",
            name="Athena 리뷰 동기화 (매일)",
            replace_existing=True,
        )

        self._scheduler.start()
        self._is_running = True

        logger.info(f"스케줄러 시작됨: 매일 {self._sync_hour:02d}:{self._sync_minute:02d}에 파이프라인 실행")
        print(f"[DailyScheduler] 파이프라인 스케줄러 시작 (매일 {self._sync_hour:02d}:{self._sync_minute:02d})")

    async def stop(self) -> None:
        """스케줄러 종료"""
        if self._is_running:
            self._scheduler.shutdown(wait=False)
            self._scheduler = AsyncIOScheduler()  # shutdown 후 재시작 위해 새 인스턴스 생성
            self._is_running = False
            logger.info("스케줄러 종료됨")
            print("[Scheduler] 리뷰 동기화 스케줄러 종료")

    async def _sync_reviews_job(self) -> None:
        """리뷰 동기화 + 파이프라인 작업 (태그/감정 분석)"""
        logger.info("스케줄러: 리뷰 파이프라인 작업 시작")
        print(f"[DailyScheduler] {utc_now().strftime('%Y-%m-%d %H:%M:%S')} - 파이프라인 시작")

        try:
            # 서비스 인스턴스 생성
            client = await get_client()
            review_repo = BranchReviewRepository(client)
            athena_client = AthenaClient()
            sync_service = SyncService(review_repo, athena_client)

            # 동기화 + 파이프라인 실행
            result = await sync_service.sync_reviews()

            if result.success:
                logger.info(
                    f"스케줄러: 파이프라인 완료 - {result.synced_count}개 저장 ({result.duration_seconds:.1f}초)"
                )
                print(
                    f"[DailyScheduler] 완료: {result.synced_count}개 저장 ({result.duration_seconds:.1f}초)"
                )
            else:
                logger.error(f"스케줄러: 파이프라인 실패 - {result.error}")
                print(f"[DailyScheduler] 실패: {result.error}")

            # 일별 태그 시간 감쇠 적용
            try:
                decay_client = await get_client()
                decay_count = await DecayJob().run(decay_client)
                logger.info(f"스케줄러: DecayJob 완료 - {decay_count}행 처리")
                print(f"[DailyScheduler] DecayJob: {decay_count}행 감쇠 적용")
            except Exception as decay_err:
                logger.warning(f"스케줄러: DecayJob 실패 (무시): {decay_err}")

        except Exception as e:
            logger.error(f"스케줄러: 파이프라인 작업 중 오류 발생 - {e}")
            print(f"[DailyScheduler] 오류: {e}")

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

    def get_schedule_time(self) -> tuple[int, int]:
        """현재 동기화 예정 시간 (시, 분) 조회"""
        return self._sync_hour, self._sync_minute

    async def update_schedule_time(self, hour: int, minute: int = 0) -> bool:
        """
        동기화 실행 시간 변경

        Args:
            hour: 시간 (0~23)
            minute: 분 (0~59)

        Returns:
            성공 여부
        """
        # 범위 검증
        if not (0 <= hour <= 23) or not (0 <= minute <= 59):
            logger.warning(f"시간 범위 초과: {hour:02d}:{minute:02d}")
            return False

        self._sync_hour = hour
        self._sync_minute = minute
        logger.info(f"스케줄러 시간 변경: 매일 {hour:02d}:{minute:02d}")
        print(f"[Scheduler] 동기화 시간 변경: 매일 {hour:02d}:{minute:02d}")

        # 실행 중이면 작업 재등록
        if self._is_running:
            self._scheduler.reschedule_job(
                "sync_reviews",
                trigger=CronTrigger(hour=hour, minute=minute, timezone="Asia/Seoul"),
            )
            logger.info(f"스케줄러 작업 재등록됨: 매일 {hour:02d}:{minute:02d}")

        return True


# 싱글톤 인스턴스
_scheduler_instance: SyncScheduler | None = None


def get_scheduler() -> SyncScheduler:
    """스케줄러 싱글톤 인스턴스 반환"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = SyncScheduler()
    return _scheduler_instance
