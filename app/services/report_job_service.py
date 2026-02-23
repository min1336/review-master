"""리포트 작업 서비스

비동기 리포트 생성 작업 관리 및 백그라운드 처리
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Awaitable
from uuid import UUID

if TYPE_CHECKING:
    from repository.report_job_repository import ReportJobRepository
    from schemas.report import ResolvedReportConfig
    from services.report_service import ReportService

logger = logging.getLogger(__name__)


class ReportJobService:
    """비동기 리포트 작업 서비스"""

    def __init__(
        self,
        job_repo: "ReportJobRepository",
        report_service: "ReportService",
    ):
        self.job_repo = job_repo
        self.report_service = report_service
        self._running_jobs: dict[str, asyncio.Task] = {}

    async def submit_job(
        self,
        branch_id: int,
        start_date: datetime,
        end_date: datetime,
        report_config: "ResolvedReportConfig | None" = None,
    ) -> str:
        """
        리포트 생성 작업 제출

        Args:
            branch_id: 지점 ID
            start_date: 시작일
            end_date: 종료일

        Returns:
            작업 ID (UUID 문자열)
        """
        # 완료된 태스크 정리
        self._cleanup_completed_tasks()

        # 동일 조건의 활성 작업이 있는지 확인 (pending 또는 processing)
        # Race condition 방지를 위해 두 상태 모두 확인
        existing = await self.job_repo.get_active_by_branch_and_period(
            branch_id, start_date, end_date
        )
        if existing:
            job_id = str(existing["id"])
            # 메모리에 없지만 pending 상태인 작업은 다시 시작
            if existing["status"] == "pending" and job_id not in self._running_jobs:
                task = asyncio.create_task(
                    self._run_job(job_id, branch_id, start_date, end_date, report_config)
                )
                self._running_jobs[job_id] = task
            return job_id

        # 새 작업 생성
        job = await self.job_repo.create(branch_id, start_date, end_date)
        if not job:
            raise RuntimeError("작업 생성 실패")

        job_id = str(job["id"])

        # 백그라운드 태스크로 리포트 생성 시작
        task = asyncio.create_task(
            self._run_job(job_id, branch_id, start_date, end_date, report_config)
        )
        self._running_jobs[job_id] = task

        return job_id

    async def get_job_status(
        self, job_id: str, branch_id: int | None = None
    ) -> dict[str, Any] | None:
        """
        작업 상태 조회

        Args:
            job_id: 작업 UUID
            branch_id: 검증할 지점 ID (선택, 제공 시 소유권 검증)

        Returns:
            작업 상태 정보 (branch_id 불일치 시 None)
        """
        job = await self.job_repo.get_by_id(job_id)
        if not job:
            return None

        # branch_id 소유권 검증
        if branch_id is not None and job.get("branch_id") != branch_id:
            return None

        return {
            "job_id": str(job["id"]),
            "branch_id": job["branch_id"],
            "status": job["status"],
            "progress": job["progress"],
            "error_message": job.get("error_message"),
            "report_id": job.get("report_id"),
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
        }

    async def _run_job(
        self,
        job_id: str,
        branch_id: int,
        start_date: datetime,
        end_date: datetime,
        report_config: "ResolvedReportConfig | None" = None,
    ) -> None:
        """
        백그라운드에서 리포트 생성 실행

        Args:
            job_id: 작업 UUID
            branch_id: 지점 ID
            start_date: 시작일
            end_date: 종료일
        """
        try:
            # 상태를 processing으로 변경
            await self.job_repo.update_status(job_id, "processing", progress=0)

            # 진행률 콜백 함수
            async def progress_callback(progress: int) -> None:
                await self.job_repo.update_progress(job_id, progress)

            # 리포트 생성 (진행률 콜백 포함)
            report = await self.report_service.generate_report_with_progress(
                branch_id=branch_id,
                start_date=start_date,
                end_date=end_date,
                progress_callback=progress_callback,
                report_config=report_config,
            )

            # 완료 상태로 변경 (report_id는 별도 저장하지 않음)
            await self.job_repo.update_status(
                job_id,
                "completed",
                progress=100,
            )

            logger.info(f"리포트 작업 완료: {job_id}")

        except Exception as e:
            # 내부 오류 상세는 로그에만 기록, 사용자에게는 일반 메시지 노출
            logger.exception(f"리포트 작업 실패: {job_id}")
            await self.job_repo.update_status(
                job_id,
                "failed",
                error_message="리포트 생성 중 오류가 발생했습니다. 다시 시도해주세요.",
            )
        finally:
            # 완료된 태스크 제거
            self._running_jobs.pop(job_id, None)

    def _cleanup_completed_tasks(self) -> None:
        """완료된 asyncio.Task 객체를 _running_jobs에서 제거"""
        done_ids = [
            job_id for job_id, task in self._running_jobs.items()
            if task.done()
        ]
        for job_id in done_ids:
            self._running_jobs.pop(job_id, None)

    async def cancel_job(self, job_id: str, branch_id: int | None = None) -> bool:
        """
        진행 중인 작업 취소

        Args:
            job_id: 작업 UUID
            branch_id: 검증할 지점 ID (선택, 제공 시 소유권 검증)

        Returns:
            취소 성공 여부
        """
        # branch_id 소유권 검증
        if branch_id is not None:
            job = await self.job_repo.get_by_id(job_id)
            if not job or job.get("branch_id") != branch_id:
                return False

        task = self._running_jobs.get(job_id)
        if task and not task.done():
            task.cancel()
            await self.job_repo.update_status(
                job_id, "failed", error_message="사용자에 의해 취소됨"
            )
            self._running_jobs.pop(job_id, None)
            return True
        return False

    async def cleanup_old_jobs(self, days: int = 7) -> int:
        """
        오래된 작업 정리

        Args:
            days: 보관 기간 (일)

        Returns:
            삭제된 작업 수
        """
        return await self.job_repo.cleanup_old_jobs(days)

    async def recover_stale_jobs(self, stale_minutes: int = 30) -> int:
        """
        고아 작업 복구 (서버 재시작 시 호출)

        processing 상태로 오래 방치된 작업들을 failed로 마킹합니다.
        서버 재시작 시 이전에 실행 중이던 작업들은 메모리에서 사라지지만
        DB에는 processing 상태로 남아있게 됩니다.

        Args:
            stale_minutes: 고아 작업으로 판단할 시간 (분)

        Returns:
            복구된 작업 수
        """
        return await self.job_repo.mark_stale_jobs_failed(
            stale_minutes=stale_minutes,
            error_message="서버 재시작으로 인한 작업 중단. 다시 시도해주세요.",
        )
