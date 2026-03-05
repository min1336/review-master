"""비동기 작업 관리 베이스 클래스

Sync/Pipeline/Upload 3개 인메모리 싱글턴 JobService의 공통 로직을 추출한다.
공통: 싱글턴, 상태 조회, 취소, 완료 작업 정리, job_id 생성
서브클래스 구현: submit_job, _run_job, _to_response
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, TypeVar
from uuid import uuid4

from core.timezone import utc_now

logger = logging.getLogger(__name__)

StateT = TypeVar("StateT", bound="BaseJobState")
ResponseT = TypeVar("ResponseT")


@dataclass
class BaseJobState:
    """인메모리 작업 상태 기본 클래스"""

    job_id: str
    status: str = "pending"  # pending | processing | completed | failed
    progress: int = 0
    message: str = ""
    error: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    last_activity_at: datetime = field(default_factory=utc_now)
    task: asyncio.Task[Any] | None = field(default=None, repr=False)


class BaseJobService(ABC, Generic[StateT, ResponseT]):
    """비동기 작업 관리 베이스 클래스 (인메모리 싱글턴)

    서브클래스는 다음을 구현해야 한다:
    - _to_response(state) -> ResponseT: 상태를 응답 DTO로 변환
    """

    _instance: BaseJobService | None = None
    _MAX_COMPLETED_JOBS = 5

    def __init__(self) -> None:
        self._jobs: dict[str, StateT] = {}

    @classmethod
    def get_instance(cls) -> BaseJobService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_job_status(self, job_id: str) -> ResponseT | None:
        """작업 상태 조회 (DB 접근 없음)"""
        state = self._jobs.get(job_id)
        if state is None:
            return None
        return self._to_response(state)

    async def cancel_job(self, job_id: str) -> bool:
        """작업 취소"""
        state = self._jobs.get(job_id)
        if state is None:
            return False

        if state.task and not state.task.done():
            state.task.cancel()
            state.status = "failed"
            state.error = "사용자에 의해 취소됨"
            logger.info("%s 작업 취소: %s", type(self).__name__, job_id)
            return True

        return False

    def _prune_old_jobs(self) -> None:
        """완료/실패 작업이 _MAX_COMPLETED_JOBS를 초과하면 오래된 것부터 제거"""
        done = [
            s for s in self._jobs.values()
            if s.status in ("completed", "failed")
        ]
        if len(done) <= self._MAX_COMPLETED_JOBS:
            return
        done.sort(key=lambda s: s.created_at)
        for s in done[: len(done) - self._MAX_COMPLETED_JOBS]:
            self._jobs.pop(s.job_id, None)

    def _generate_job_id(self) -> str:
        """12자리 hex job_id 생성"""
        return uuid4().hex[:12]

    def _find_active_job(self) -> StateT | None:
        """활성(pending/processing) 작업이 있으면 반환"""
        for job in self._jobs.values():
            if job.status in ("pending", "processing"):
                return job
        return None

    @abstractmethod
    def _to_response(self, state: StateT) -> ResponseT:
        """상태를 응답 DTO로 변환"""
        ...
