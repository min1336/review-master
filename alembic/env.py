import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# app/ 디렉토리를 sys.path에 추가 (app 내부 import 호환)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from core.config import get_settings
from repository.orm_models import Base

# Alembic Config 객체
config = context.config

# 로깅 설정
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# .env에서 DATABASE_URL 로드하여 Alembic에 주입
# ConfigParser의 % interpolation 충돌 방지: %% 이스케이프
settings = get_settings()
database_url = settings.get_database_url()
if database_url:
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

# autogenerate 대상 메타데이터
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """오프라인 모드: SQL 스크립트만 생성 (DB 연결 불필요)"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """온라인 모드: async 엔진으로 DB에 직접 마이그레이션 실행"""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
