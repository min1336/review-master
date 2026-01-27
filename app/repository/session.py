"""
Supabase 비동기 클라이언트 싱글톤 (연결 안정성 강화)

HTTP/2 연결 끊김 문제 해결:
- 타임아웃 설정 (connect=10s, read/write=30s)
- 연결 풀 관리 (max=50, keepalive=10)
- HTTP/2 비활성화 (안정성 향상)
- 재시도 로직 (3회, 지수 백오프)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import TypeVar

import httpx
from core.config import get_settings
from supabase import AsyncClient, acreate_client

logger = logging.getLogger(__name__)

# HTTP 클라이언트 설정
HTTP_TIMEOUT = httpx.Timeout(
    connect=10.0,
    read=30.0,
    write=30.0,
    pool=5.0,
)

HTTP_LIMITS = httpx.Limits(
    max_connections=50,
    max_keepalive_connections=10,
    keepalive_expiry=30.0,
)

# 재시도 대상 예외
RETRYABLE_EXCEPTIONS = (
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
)

T = TypeVar("T")


class DatabaseConnection:
    """
    Supabase 비동기 클라이언트 싱글톤 관리자

    이벤트 루프별 클라이언트 관리:
    - 클라이언트가 다른 이벤트 루프에서 생성되었으면 재생성
    - 스케줄러(sync)와 FastAPI(async) 컨텍스트 충돌 방지
    """

    _instance: DatabaseConnection | None = None
    _client: AsyncClient | None = None
    _client_loop: asyncio.AbstractEventLoop | None = None

    def __new__(cls) -> DatabaseConnection:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @staticmethod
    def _create_httpx_client() -> httpx.AsyncClient:
        """연결 재시도와 최적화된 설정의 async httpx 클라이언트 생성"""
        transport = httpx.AsyncHTTPTransport(retries=3)
        return httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            limits=HTTP_LIMITS,
            transport=transport,
            http2=False,
        )

    async def get_client(self) -> AsyncClient:
        """Supabase 비동기 클라이언트 획득"""
        settings = get_settings()

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        # 클라이언트가 다른 이벤트 루프에서 생성되었으면 재생성
        loop_changed = (
            self._client is not None
            and self._client_loop is not None
            and self._client_loop != current_loop
        )
        if loop_changed:
            logger.debug("이벤트 루프 변경 감지, 클라이언트 재생성")
            await self._close_client()

        if self._client is None:
            supabase_key = settings.supabase_key.get_secret_value()
            if not settings.supabase_url or not supabase_key:
                raise ValueError("SUPABASE_URL과 SUPABASE_KEY 환경변수가 필요합니다")

            self._client = await acreate_client(settings.supabase_url, supabase_key)
            self._client.postgrest._session = self._create_httpx_client()
            self._client_loop = current_loop

        return self._client

    async def _close_client(self) -> None:
        """클라이언트 연결 종료"""
        if self._client is not None:
            with contextlib.suppress(Exception):
                await self._client.postgrest._session.aclose()
        self._client = None
        self._client_loop = None

    async def reset(self) -> None:
        """클라이언트 재생성 (연결 문제 발생 시 호출)"""
        await self._close_client()
        logger.info("Database connection reset")


# 싱글톤 인스턴스
_db = DatabaseConnection()


async def get_client() -> AsyncClient:
    """Supabase 비동기 클라이언트 획득 (편의 함수)"""
    return await _db.get_client()


async def reset_client() -> None:
    """클라이언트 재생성 (연결 문제 발생 시 호출)"""
    await _db.reset()


async def execute_with_retry(
    query, max_attempts: int = 3, min_wait: float = 0.5, max_wait: float = 4.0
):
    """
    Supabase 비동기 쿼리 실행 (재시도 포함)

    Args:
        query: Supabase 쿼리 객체 (.execute() 호출 전)
        max_attempts: 최대 시도 횟수 (기본 3)
        min_wait: 최소 대기 시간 (초)
        max_wait: 최대 대기 시간 (초)

    Returns:
        쿼리 실행 결과
    """
    last_exception = None

    for attempt in range(max_attempts):
        try:
            return await query.execute()
        except RETRYABLE_EXCEPTIONS as e:
            last_exception = e
            wait_time = min(min_wait * (2**attempt), max_wait)

            logger.warning(
                f"Supabase 연결 오류 (시도 {attempt + 1}/{max_attempts}): {e}"
            )

            if attempt < max_attempts - 1:
                await reset_client()
                await asyncio.sleep(wait_time)
            else:
                logger.error("최대 재시도 횟수 초과")
                raise

    raise last_exception


def with_retry(
    max_attempts: int = 3, min_wait: float = 0.5, max_wait: float = 4.0
) -> Callable:
    """
    Supabase 비동기 쿼리용 재시도 데코레이터

    Args:
        max_attempts: 최대 시도 횟수 (기본 3)
        min_wait: 최소 대기 시간 (초)
        max_wait: 최대 대기 시간 (초)
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except RETRYABLE_EXCEPTIONS as e:
                    last_exception = e
                    wait_time = min(min_wait * (2**attempt), max_wait)

                    logger.warning(
                        f"Supabase 연결 오류 (시도 {attempt + 1}/{max_attempts}): {e}"
                    )

                    if attempt < max_attempts - 1:
                        await reset_client()
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"최대 재시도 횟수 초과: {func.__name__}")
                        raise

            raise last_exception

        return wrapper

    return decorator
