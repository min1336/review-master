"""
Repository 기본 추상 클래스
SQLAlchemy AsyncSession 기반 Generic Repository 패턴
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .orm_models import Base

logger = logging.getLogger(__name__)


class BaseRepository[T: BaseModel](ABC):
    """
    Repository 기본 추상 클래스

    모든 Repository는 이 클래스를 상속하여 구현합니다.
    AsyncSession을 주입받아 사용하고, Pydantic 모델을 반환합니다.

    Usage:
        class SummaryRepository(BaseRepository[Summary]):
            model = Summary
            orm_model = BranchSummaryORM

            @property
            def table_name(self) -> str:
                return "branch_summaries"
    """

    model: type[T]  # Pydantic 모델 (구체 클래스에서 지정)
    orm_model: type[Base]  # ORM 모델 (구체 클래스에서 지정)

    def __init__(self, session: AsyncSession):
        self._session = session

    @property
    @abstractmethod
    def table_name(self) -> str:
        """테이블 이름 반환"""
        pass

    def _to_pydantic(self, row: Base) -> T:
        """ORM 행 → Pydantic 모델 변환"""
        return self.model.model_validate(row, from_attributes=True)

    def _to_dict(self, row: Base) -> dict[str, Any]:
        """ORM 행 → dict 변환"""
        return {
            c.key: getattr(row, c.key)
            for c in row.__table__.columns
        }

    async def get_by_id(self, id: int) -> T | None:
        """ID로 단일 조회"""
        try:
            result = await self._session.execute(
                select(self.orm_model).where(self.orm_model.id == id)
            )
            row = result.scalar_one_or_none()
            return self._to_pydantic(row) if row else None
        except Exception as e:
            logger.error("get_by_id(%s) 실패: %s", id, e)
            return None

    async def get_all(self, limit: int = 100, offset: int = 0) -> list[T]:
        """전체 목록 조회"""
        result = await self._session.execute(
            select(self.orm_model).offset(offset).limit(limit)
        )
        return [self._to_pydantic(row) for row in result.scalars().all()]

    async def create(self, data: T) -> T:
        """생성"""
        stmt = (
            pg_insert(self.orm_model.__table__)
            .values(**data.model_dump(exclude_unset=True, exclude_none=True))
            .returning(self.orm_model.__table__)
        )
        result = await self._session.execute(stmt)
        row = result.mappings().one()
        return self.model(**row)

    async def create_dict(self, data: dict) -> T | None:
        """dict로 생성"""
        stmt = (
            pg_insert(self.orm_model.__table__)
            .values(**data)
            .returning(self.orm_model.__table__)
        )
        result = await self._session.execute(stmt)
        row = result.mappings().one_or_none()
        return self.model(**row) if row else None

    async def update(self, id: int, data: dict) -> T | None:
        """수정"""
        stmt = (
            update(self.orm_model)
            .where(self.orm_model.id == id)
            .values(**data)
            .returning(self.orm_model.__table__)
        )
        result = await self._session.execute(stmt)
        row = result.mappings().one_or_none()
        return self.model(**row) if row else None

    async def delete(self, id: int) -> bool:
        """삭제"""
        stmt = (
            delete(self.orm_model)
            .where(self.orm_model.id == id)
            .returning(self.orm_model.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def upsert(self, data: dict, on_conflict: str = "id") -> T | None:
        """저장/업데이트"""
        conflict_cols = [c.strip() for c in on_conflict.split(",")]
        stmt = pg_insert(self.orm_model.__table__).values(**data)
        update_cols = {
            k: v for k, v in data.items() if k not in conflict_cols
        }
        if update_cols:
            stmt = stmt.on_conflict_do_update(
                index_elements=conflict_cols,
                set_=update_cols,
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=conflict_cols)
        stmt = stmt.returning(self.orm_model.__table__)
        result = await self._session.execute(stmt)
        row = result.mappings().one_or_none()
        return self.model(**row) if row else None

    async def count(self) -> int:
        """전체 개수 조회"""
        result = await self._session.execute(
            select(func.count()).select_from(self.orm_model)
        )
        return result.scalar_one()
