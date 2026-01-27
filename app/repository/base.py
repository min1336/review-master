"""
Repository 기본 추상 클래스
Pydantic 모델과 연결된 Generic Repository 패턴
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel
from supabase import AsyncClient


class BaseRepository[T: BaseModel](ABC):
    """
    Repository 기본 추상 클래스

    모든 Repository는 이 클래스를 상속하여 구현합니다.
    AsyncClient를 주입받아 사용하고, Pydantic 모델을 반환합니다.

    Usage:
        class SummaryRepository(BaseRepository[Summary]):
            model = Summary

            @property
            def table_name(self) -> str:
                return "branch_summaries"
    """

    model: type[T]  # 구체 클래스에서 지정

    def __init__(self, client: AsyncClient):
        self._client = client

    @property
    @abstractmethod
    def table_name(self) -> str:
        """테이블 이름 반환"""
        pass

    async def get_by_id(self, id: int) -> T | None:
        """ID로 단일 조회"""
        try:
            result = (
                await self._client.table(self.table_name)
                .select("*")
                .eq("id", id)
                .single()
                .execute()
            )
            return self.model(**result.data) if result.data else None
        except Exception:
            return None

    async def get_all(self, limit: int = 100, offset: int = 0) -> list[T]:
        """전체 목록 조회"""
        result = (
            await self._client.table(self.table_name)
            .select("*")
            .range(offset, offset + limit - 1)
            .execute()
        )
        return [self.model(**row) for row in result.data]

    async def create(self, data: T) -> T:
        """생성"""
        result = (
            await self._client.table(self.table_name)
            .insert(data.model_dump(exclude_unset=True, exclude_none=True))
            .execute()
        )
        return self.model(**result.data[0])

    async def create_dict(self, data: dict) -> T | None:
        """dict로 생성"""
        result = await self._client.table(self.table_name).insert(data).execute()
        return self.model(**result.data[0]) if result.data else None

    async def update(self, id: int, data: dict) -> T | None:
        """수정"""
        result = (
            await self._client.table(self.table_name)
            .update(data)
            .eq("id", id)
            .execute()
        )
        return self.model(**result.data[0]) if result.data else None

    async def delete(self, id: int) -> bool:
        """삭제"""
        result = (
            await self._client.table(self.table_name).delete().eq("id", id).execute()
        )
        return len(result.data) > 0 if result.data else False

    async def upsert(self, data: dict, on_conflict: str = "id") -> T | None:
        """저장/업데이트"""
        result = (
            await self._client.table(self.table_name)
            .upsert(data, on_conflict=on_conflict)
            .execute()
        )
        return self.model(**result.data[0]) if result.data else None

    async def count(self) -> int:
        """전체 개수 조회"""
        result = (
            await self._client.table(self.table_name)
            .select("id", count="exact")
            .execute()
        )
        return result.count or 0
