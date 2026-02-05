"""월간 AI 스케줄러 - 매월 1일 실행"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.config import get_settings
from repository.session import get_client
from repository.summary_repository import SummaryRepository
from repository.review_repository import BranchReviewRepository
from repository.branch_tag_repository import BranchTagRepository
from repository.report_repository import ReportRepository
from repository.sentiment_repository import SentimentRepository
from repository.sync_metadata_repository import SyncMetadataRepository
from services.report_service import ReportService
from services.summary_service import SummaryService

logger = logging.getLogger(__name__)

SYNC_TYPE = "monthly_ai"


class MonthlyScheduler:
    """월간 AI 스케줄러 - 매월 1일 새벽에 AI 요약/리포트 생성"""

    # 기본 실행 시간 (매월 1일 새벽 3시)
    DEFAULT_DAY = 1
    DEFAULT_HOUR = 3
    DEFAULT_MINUTE = 0

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._settings = get_settings()
        self._is_running = False
        self._run_day = self.DEFAULT_DAY
        self._run_hour = self.DEFAULT_HOUR
        self._run_minute = self.DEFAULT_MINUTE

    async def start(self) -> None:
        """스케줄러 시작"""
        if not self._settings.scheduler_enabled:
            logger.info("스케줄러가 비활성화되어 있습니다 (SCHEDULER_ENABLED=false)")
            return

        # 월간 AI 작업 등록 - 매월 1일
        self._scheduler.add_job(
            self._monthly_ai_job,
            trigger=CronTrigger(
                day=self._run_day,
                hour=self._run_hour,
                minute=self._run_minute,
            ),
            id="monthly_ai",
            name="월간 AI 요약/리포트 생성",
            replace_existing=True,
        )

        self._scheduler.start()
        self._is_running = True

        logger.info(
            f"월간 스케줄러 시작됨: 매월 {self._run_day}일 "
            f"{self._run_hour:02d}:{self._run_minute:02d}에 실행"
        )
        print(
            f"[MonthlyScheduler] 스케줄러 시작 "
            f"(매월 {self._run_day}일 {self._run_hour:02d}:{self._run_minute:02d})"
        )

    async def stop(self) -> None:
        """스케줄러 종료"""
        if self._is_running:
            self._scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("월간 스케줄러 종료됨")
            print("[MonthlyScheduler] 스케줄러 종료")

    async def _monthly_ai_job(self) -> None:
        """월간 AI 요약/리포트 생성 작업"""
        logger.info("월간 스케줄러: AI 작업 시작")
        print(
            f"[MonthlyScheduler] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - AI 작업 시작"
        )

        try:
            client = await get_client()
            metadata_repo = SyncMetadataRepository(client)

            # 락 획득
            lock_acquired = await metadata_repo.acquire_lock(SYNC_TYPE)
            if not lock_acquired:
                logger.warning("월간 스케줄러: 다른 AI 작업이 실행 중입니다. 건너뜁니다.")
                print("[MonthlyScheduler] 다른 작업 실행 중 - 건너뜀")
                return

            try:
                # Repository 생성
                summary_repo = SummaryRepository(client)
                review_repo = BranchReviewRepository(client)
                branch_tag_repo = BranchTagRepository(client)
                report_repo = ReportRepository(client)
                sentiment_repo = SentimentRepository(client)

                # ReportService 생성
                report_service = ReportService(
                    summary_repo, review_repo, branch_tag_repo, report_repo, sentiment_repo
                )

                # SummaryService 생성 (pending 요약용)
                summary_service = SummaryService(
                    summary_repo, review_repo, branch_tag_repo, sentiment_repo
                )

                # 지난 달 기간 계산
                today = datetime.now()
                first_day_this_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                last_day_last_month = first_day_this_month - timedelta(days=1)
                first_day_last_month = last_day_last_month.replace(day=1)

                logger.info(
                    f"월간 AI 생성 기간: {first_day_last_month.date()} ~ {last_day_last_month.date()}"
                )
                print(
                    f"[MonthlyScheduler] 기간: {first_day_last_month.date()} ~ {last_day_last_month.date()}"
                )

                # 리뷰가 있는 모든 지점 조회
                branch_stats = await review_repo.get_stats()
                branch_ids = [b["branch_id"] for b in branch_stats if b.get("review_count", 0) >= 10]

                logger.info(f"대상 지점: {len(branch_ids)}개")
                print(f"[MonthlyScheduler] 대상 지점: {len(branch_ids)}개")

                # 1단계: 각 지점에 대해 리포트 생성
                report_success = 0
                report_fail = 0

                logger.info("월간 스케줄러: 리포트 생성 시작")
                print("[MonthlyScheduler] 1/2 리포트 생성 시작...")

                for i, branch_id in enumerate(branch_ids):
                    try:
                        # 리포트 생성 (저장 포함)
                        report, is_new = await report_service.get_or_generate_report(
                            branch_id=branch_id,
                            start_date=first_day_last_month,
                            end_date=last_day_last_month,
                        )

                        if is_new:
                            report_success += 1

                        # 진행 로그 (10개마다)
                        if (i + 1) % 10 == 0:
                            print(f"[MonthlyScheduler] 리포트 진행: {i + 1}/{len(branch_ids)}")

                    except Exception as e:
                        logger.warning(f"리포트 생성 실패 (branch_id={branch_id}): {e}")
                        report_fail += 1

                logger.info(f"리포트 생성 완료: {report_success}개 생성, {report_fail}개 실패")
                print(f"[MonthlyScheduler] 리포트 완료: {report_success}개 생성, {report_fail}개 실패")

                # 2단계: 각 지점에 대해 pending 요약 생성
                summary_success = 0
                summary_fail = 0

                logger.info("월간 스케줄러: Pending 요약 생성 시작")
                print("[MonthlyScheduler] 2/2 Pending 요약 생성 시작...")

                for i, branch_id in enumerate(branch_ids):
                    try:
                        # pending 요약 생성
                        result = await summary_service.generate_pending_summary(branch_id)

                        if result.get("success"):
                            summary_success += 1
                        else:
                            # 리뷰 부족 등의 이유로 실패
                            pass

                        # 진행 로그 (10개마다)
                        if (i + 1) % 10 == 0:
                            print(f"[MonthlyScheduler] 요약 진행: {i + 1}/{len(branch_ids)}")

                    except Exception as e:
                        logger.warning(f"Pending 요약 생성 실패 (branch_id={branch_id}): {e}")
                        summary_fail += 1

                logger.info(f"Pending 요약 생성 완료: {summary_success}개 생성, {summary_fail}개 실패")
                print(f"[MonthlyScheduler] Pending 요약 완료: {summary_success}개 생성, {summary_fail}개 실패")

                # 동기화 시간 업데이트
                await metadata_repo.update_last_sync_at(SYNC_TYPE)

                logger.info(
                    f"월간 스케줄러: AI 작업 완료 - "
                    f"리포트 {report_success}개, 요약 {summary_success}개 생성"
                )
                print(
                    f"[MonthlyScheduler] 전체 완료: "
                    f"리포트 {report_success}개, 요약 {summary_success}개 생성"
                )

            finally:
                # 락 해제
                await metadata_repo.release_lock(SYNC_TYPE)

        except Exception as e:
            logger.error(f"월간 스케줄러: AI 작업 중 오류 발생 - {e}")
            print(f"[MonthlyScheduler] 오류: {e}")

    async def run_now(self) -> dict:
        """수동 실행"""
        await self._monthly_ai_job()
        return {"message": "월간 AI 작업 완료"}

    @property
    def is_running(self) -> bool:
        """스케줄러 실행 상태"""
        return self._is_running

    def get_next_run_time(self) -> datetime | None:
        """다음 실행 시간 조회"""
        if not self._is_running:
            return None

        job = self._scheduler.get_job("monthly_ai")
        if job:
            return job.next_run_time
        return None

    def get_schedule_info(self) -> dict:
        """스케줄 정보 조회"""
        return {
            "day": self._run_day,
            "hour": self._run_hour,
            "minute": self._run_minute,
        }

    async def update_schedule(
        self, day: int = 1, hour: int = 3, minute: int = 0
    ) -> bool:
        """
        실행 시간 변경

        Args:
            day: 일 (1~28)
            hour: 시 (0~23)
            minute: 분 (0~59)

        Returns:
            성공 여부
        """
        if not (1 <= day <= 28) or not (0 <= hour <= 23) or not (0 <= minute <= 59):
            logger.warning(f"범위 초과: {day}일 {hour:02d}:{minute:02d}")
            return False

        self._run_day = day
        self._run_hour = hour
        self._run_minute = minute

        logger.info(f"월간 스케줄러 시간 변경: 매월 {day}일 {hour:02d}:{minute:02d}")
        print(f"[MonthlyScheduler] 시간 변경: 매월 {day}일 {hour:02d}:{minute:02d}")

        # 실행 중이면 작업 재등록
        if self._is_running:
            self._scheduler.reschedule_job(
                "monthly_ai",
                trigger=CronTrigger(day=day, hour=hour, minute=minute),
            )

        return True


# 싱글톤 인스턴스
_scheduler_instance: MonthlyScheduler | None = None


def get_monthly_scheduler() -> MonthlyScheduler:
    """스케줄러 싱글톤 인스턴스 반환"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = MonthlyScheduler()
    return _scheduler_instance
