"""
Supabase 비동기 클라이언트 싱글톤 (연결 안정성 강화)

HTTP/2 연결 끊김 문제 해결:
- 타임아웃 설정 (connect=10s, read/write=30s)
- 연결 풀 관리 (max=50, keepalive=10)
- HTTP/2 비활성화 (안정성 향상)
- 재시도 로직 (3회, 지수 백오프)
"""
import asyncio
import logging
from functools import wraps
from typing import TypeVar, Callable, Awaitable

import httpx
from supabase import acreate_client, AsyncClient

from core.config import get_settings

logger = logging.getLogger(__name__)

# HTTP 클라이언트 설정
HTTP_TIMEOUT = httpx.Timeout(
    connect=10.0,    # 연결 타임아웃
    read=30.0,       # 읽기 타임아웃
    write=30.0,      # 쓰기 타임아웃
    pool=5.0         # 풀에서 연결 획득 타임아웃
)

HTTP_LIMITS = httpx.Limits(
    max_connections=50,           # 최대 연결 수
    max_keepalive_connections=10, # Keep-alive 연결 수
    keepalive_expiry=30.0         # Keep-alive 만료 시간 (초)
)

# 재시도 대상 예외
RETRYABLE_EXCEPTIONS = (
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
)

_client: AsyncClient = None
_client_loop = None  # 클라이언트가 생성된 이벤트 루프


def _create_async_httpx_client() -> httpx.AsyncClient:
    """연결 재시도와 최적화된 설정의 async httpx 클라이언트 생성"""
    transport = httpx.AsyncHTTPTransport(
        retries=3,  # 연결 에러 시 3회 재시도
    )

    return httpx.AsyncClient(
        timeout=HTTP_TIMEOUT,
        limits=HTTP_LIMITS,
        transport=transport,
        http2=False,  # HTTP/2 비활성화로 연결 안정성 향상
    )


async def get_client() -> AsyncClient:
    """
    Supabase 비동기 클라이언트 싱글톤 (안정성 강화)

    이벤트 루프별로 클라이언트 관리:
    - 클라이언트가 다른 이벤트 루프에서 생성되었으면 재생성
    - 스케줄러(sync)와 FastAPI(async) 컨텍스트 충돌 방지
    """
    global _client, _client_loop

    settings = get_settings()

    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    # 클라이언트가 다른 이벤트 루프에서 생성되었으면 재생성
    if _client is not None and _client_loop is not None and _client_loop != current_loop:
        logger.debug("이벤트 루프 변경 감지, 클라이언트 재생성")
        try:
            await _client.postgrest._session.aclose()
        except Exception:
            pass
        _client = None

    if _client is None:
        if not settings.supabase_url or not settings.supabase_key:
            raise ValueError("SUPABASE_URL과 SUPABASE_KEY 환경변수가 필요합니다")

        _client = await acreate_client(settings.supabase_url, settings.supabase_key)

        # httpx 클라이언트 교체 (연결 안정성 설정 적용)
        custom_httpx = _create_async_httpx_client()
        _client.postgrest._session = custom_httpx

    return _client


async def reset_client():
    """클라이언트 재생성 (연결 문제 발생 시 호출)"""
    global _client, _client_loop
    if _client is not None:
        try:
            await _client.postgrest._session.aclose()
        except Exception:
            pass
    _client = None
    _client_loop = None


T = TypeVar('T')


async def execute_with_retry(
    query,
    max_attempts: int = 3,
    min_wait: float = 0.5,
    max_wait: float = 4.0
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
            wait_time = min(min_wait * (2 ** attempt), max_wait)

            logger.warning(
                f"Supabase 연결 오류 (시도 {attempt + 1}/{max_attempts}): {e}"
            )

            if attempt < max_attempts - 1:
                await reset_client()
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"최대 재시도 횟수 초과")
                raise

    raise last_exception


def with_retry(
    max_attempts: int = 3,
    min_wait: float = 0.5,
    max_wait: float = 4.0
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
                    wait_time = min(min_wait * (2 ** attempt), max_wait)

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
