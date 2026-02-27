"""
SQLAlchemy Async 엔진/세션 팩토리

PostgreSQL(asyncpg) 직접 TCP 연결 관리:
- 커넥션 풀 (pool_size=3, max_overflow=2)
- pool_pre_ping으로 끊어진 연결 자동 감지
- 재시도 데코레이터 (asyncpg 연결 오류 대상)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from functools import wraps
from typing import TypeVar

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

# 모듈 레벨 싱글톤
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None

# 재시도 대상 예외
RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = ()

def _load_retryable_exceptions() -> tuple[type[Exception], ...]:
    """asyncpg 예외를 런타임에 로드 (import 순서 문제 방지)"""
    try:
        import asyncpg
        from sqlalchemy.exc import OperationalError

        return (
            asyncpg.InterfaceError,
            asyncpg.ConnectionDoesNotExistError,
            asyncpg.TooManyConnectionsError,
            OperationalError,
            OSError,
        )
    except ImportError:
        from sqlalchemy.exc import OperationalError

        return (OperationalError, OSError)


def init_db(database_url: str) -> None:
    """
    SQLAlchemy 엔진 및 세션 팩토리 초기화

    Args:
        database_url: postgresql+asyncpg://user:pass@host:port/dbname
    """
    global _engine, _session_factory, RETRYABLE_EXCEPTIONS

    if _engine is not None:
        logger.warning("Database already initialized, skipping")
        return

    if not database_url:
        raise ValueError("DATABASE_URL 환경변수가 필요합니다")

    # Supabase Pooler(Transaction mode)에서는 prepared statement 비활성화 필요
    connect_args = {}
    if "pooler.supabase" in database_url or ":6543" in database_url:
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_cache_size"] = 0

    _engine = create_async_engine(
        database_url,
        pool_size=3,
        max_overflow=2,
        pool_timeout=30,
        pool_pre_ping=True,
        pool_recycle=1800,
        echo=False,
        connect_args=connect_args,
    )

    _session_factory = async_sessionmaker(
        bind=_engine,
        expire_on_commit=False,
    )

    RETRYABLE_EXCEPTIONS = _load_retryable_exceptions()

    logger.info("Database engine initialized: pool_size=3, max_overflow=2")


async def close_db() -> None:
    """엔진 종료 및 커넥션 풀 정리"""
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database engine closed")


def get_engine() -> AsyncEngine:
    """현재 엔진 반환"""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """세션 팩토리 반환"""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI Depends용 세션 제너레이터

    Usage:
        async def get_repo(session: AsyncSession = Depends(get_session)):
            return SomeRepository(session)
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def with_retry(
    max_attempts: int = 3, min_wait: float = 0.5, max_wait: float = 4.0
) -> Callable:
    """
    asyncpg 연결 오류용 재시도 데코레이터

    Args:
        max_attempts: 최대 시도 횟수
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
                        "DB connection error (attempt %d/%d): %s",
                        attempt + 1, max_attempts, e,
                    )

                    if attempt < max_attempts - 1:
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error("Max retries exceeded: %s", func.__name__)
                        raise

            raise last_exception  # type: ignore[misc]

        return wrapper

    return decorator
