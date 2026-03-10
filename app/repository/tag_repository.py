"""
태그/카테고리/매핑 Repository
"""

from __future__ import annotations

import logging

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload

from models.tag import Category, KeywordMapping, Tag

from .base import BaseRepository
from .orm_models import (
    BranchKeywordORM,
    CategoryORM,
    KeywordMappingORM,
    TagORM,
)

logger = logging.getLogger(__name__)


class TagRepository(BaseRepository[Tag]):
    """tags 테이블 Repository"""

    model = Tag
    orm_model = TagORM

    @property
    def table_name(self) -> str:
        return "tags"

    def _tag_from_orm(self, row: TagORM) -> Tag:
        """TagORM -> Tag Pydantic 변환 (category 관계 포함)"""
        data = {
            c.key: getattr(row, c.key)
            for c in TagORM.__table__.columns
        }
        if row.category is not None:
            data["categories"] = Category.model_validate(
                row.category, from_attributes=True
            )
        return Tag(**data)

    def _build_filter_stmt(
        self,
        category_id: int | None = None,
        sentiment: str | None = None,
        group_name: str | None = None,
        is_active: bool = True,
    ):
        """공통 필터 조건을 적용한 base statement 반환 (select 컬럼은 호출처에서 결정)"""
        stmt = select(TagORM)

        if group_name:
            stmt = stmt.where(TagORM.group_name == group_name)
        elif category_id is not None:
            stmt = stmt.options(selectinload(TagORM.category))
            stmt = stmt.where(TagORM.category_id == category_id)
        if sentiment:
            stmt = stmt.where(TagORM.sentiment == sentiment)
        if is_active is not None:
            stmt = stmt.where(TagORM.is_active == is_active)

        return stmt

    async def get_all_with_filters(
        self,
        category_id: int | None = None,
        sentiment: str | None = None,
        group_name: str | None = None,
        is_active: bool = True,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[Tag]:
        """필터링된 태그 목록 (DB-level 페이지네이션 지원)"""
        stmt = self._build_filter_stmt(
            category_id=category_id,
            sentiment=sentiment,
            group_name=group_name,
            is_active=is_active,
        )
        stmt = stmt.order_by(TagORM.name)

        if offset is not None:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await self._session.execute(stmt)
        rows = result.scalars().all()

        if category_id is not None:
            return [self._tag_from_orm(row) for row in rows]
        return [self._to_pydantic(row) for row in rows]

    async def count_with_filters(
        self,
        category_id: int | None = None,
        sentiment: str | None = None,
        group_name: str | None = None,
        is_active: bool = True,
    ) -> int:
        """필터 조건에 맞는 태그 총 개수"""
        stmt = select(func.count(TagORM.id))

        if group_name:
            stmt = stmt.where(TagORM.group_name == group_name)
        elif category_id is not None:
            stmt = stmt.where(TagORM.category_id == category_id)
        if sentiment:
            stmt = stmt.where(TagORM.sentiment == sentiment)
        if is_active is not None:
            stmt = stmt.where(TagORM.is_active == is_active)

        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get_by_name(self, name: str) -> Tag | None:
        """이름으로 조회"""
        result = await self._session.execute(
            select(TagORM).where(TagORM.name == name)
        )
        row = result.scalar_one_or_none()
        return self._to_pydantic(row) if row else None

    async def get_with_category(self, tag_id: int) -> Tag | None:
        """카테고리 정보와 함께 조회"""
        result = await self._session.execute(
            select(TagORM)
            .options(selectinload(TagORM.category))
            .where(TagORM.id == tag_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._tag_from_orm(row)

    async def get_or_create(
        self, name: str, category_id: int | None = None, sentiment: str = "positive"
    ) -> Tag:
        """조회 또는 생성"""
        existing = await self.get_by_name(name)
        if existing:
            return existing

        stmt = (
            pg_insert(TagORM.__table__)
            .values(name=name, category_id=category_id, sentiment=sentiment)
            .returning(TagORM.__table__)
        )
        result = await self._session.execute(stmt)
        row = result.mappings().one()
        return Tag(**row)

    async def get_groups(self) -> list[dict]:
        """고유 그룹 목록 (DB 집계)"""
        stmt = (
            select(
                func.coalesce(TagORM.group_name, "기타").label("gname"),
                func.min(TagORM.color).label("color"),
                func.count().label("cnt"),
            )
            .where(TagORM.is_active == True)
            .group_by(func.coalesce(TagORM.group_name, "기타"))
        )
        result = await self._session.execute(stmt)
        return [
            {
                "group_name": row.gname,
                "color": row.color or "#667eea",
                "count": row.cnt,
            }
            for row in result.all()
        ]


class CategoryRepository(BaseRepository[Category]):
    """categories 테이블 Repository"""

    model = Category
    orm_model = CategoryORM

    @property
    def table_name(self) -> str:
        return "categories"

    async def get_all_active(self, is_active: bool = True) -> list[Category]:
        """활성 카테고리 목록"""
        stmt = select(CategoryORM)
        if is_active is not None:
            stmt = stmt.where(CategoryORM.is_active == is_active)
        stmt = stmt.order_by(CategoryORM.display_order)

        result = await self._session.execute(stmt)
        return [self._to_pydantic(row) for row in result.scalars().all()]

    async def delete_with_tags(self, category_id: int) -> bool:
        """카테고리 삭제 (소속 태그는 미분류로)"""
        # 소속 태그의 category_id를 null로
        await self._session.execute(
            update(TagORM)
            .where(TagORM.category_id == category_id)
            .values(category_id=None)
        )
        # 카테고리 삭제
        result = await self._session.execute(
            delete(CategoryORM).where(CategoryORM.id == category_id)
        )
        return result.rowcount > 0


class MappingRepository(BaseRepository[KeywordMapping]):
    """keyword_mappings 테이블 Repository"""

    model = KeywordMapping
    orm_model = KeywordMappingORM

    @property
    def table_name(self) -> str:
        return "keyword_mappings"

    def _mapping_from_orm(self, row: KeywordMappingORM) -> KeywordMapping:
        """KeywordMappingORM -> KeywordMapping Pydantic 변환 (tag 관계 포함)"""
        data = {
            c.key: getattr(row, c.key)
            for c in KeywordMappingORM.__table__.columns
        }
        if row.tag is not None:
            data["tags"] = Tag.model_validate(row.tag, from_attributes=True)
        return KeywordMapping(**data)

    async def get_mappings(
        self, tag_id: int | None = None, keyword: str | None = None
    ) -> list[KeywordMapping]:
        """매핑 목록 조회"""
        stmt = (
            select(KeywordMappingORM)
            .options(selectinload(KeywordMappingORM.tag))
        )

        if tag_id is not None:
            stmt = stmt.where(KeywordMappingORM.tag_id == tag_id)
        if keyword:
            stmt = stmt.where(KeywordMappingORM.keyword == keyword)

        stmt = stmt.order_by(KeywordMappingORM.keyword)
        result = await self._session.execute(stmt)
        return [self._mapping_from_orm(row) for row in result.scalars().all()]

    async def upsert_mapping(
        self, keyword: str, tag_id: int, is_auto: bool = True, confidence: float = 1.0
    ) -> KeywordMapping | None:
        """매핑 생성/업데이트 (keyword UNIQUE 기준)"""
        stmt = (
            pg_insert(KeywordMappingORM.__table__)
            .values(
                keyword=keyword,
                tag_id=tag_id,
                is_auto=is_auto,
                confidence=confidence,
            )
            .on_conflict_do_update(
                index_elements=["keyword"],
                set_={
                    "tag_id": tag_id,
                    "is_auto": is_auto,
                    "confidence": confidence,
                },
            )
            .returning(KeywordMappingORM.__table__)
        )
        result = await self._session.execute(stmt)
        row = result.mappings().one_or_none()
        return KeywordMapping(**row) if row else None

    async def delete_by_keyword(self, keyword: str, tag_id: int) -> bool:
        """키워드와 태그 ID로 삭제"""
        result = await self._session.execute(
            delete(KeywordMappingORM)
            .where(KeywordMappingORM.keyword == keyword)
            .where(KeywordMappingORM.tag_id == tag_id)
        )
        return result.rowcount > 0

    async def get_unmapped_keywords(self, limit: int = 100) -> list[dict]:
        """매핑되지 않은 키워드 목록 (단일 쿼리 최적화)"""
        mapped_subq = select(KeywordMappingORM.keyword)
        stmt = (
            select(
                BranchKeywordORM.keyword,
                func.sum(BranchKeywordORM.count).label("total_count"),
            )
            .where(BranchKeywordORM.keyword.notin_(mapped_subq))
            .group_by(BranchKeywordORM.keyword)
            .order_by(func.sum(BranchKeywordORM.count).desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [
            {"keyword": row.keyword, "count": int(row.total_count)}
            for row in result.all()
        ]

    async def bulk_create(self, mappings: list[dict]) -> int:
        """일괄 생성"""
        if not mappings:
            return 0

        rows = [
            {
                "keyword": m["keyword"],
                "tag_id": m["tag_id"],
                "is_auto": m.get("is_auto", True),
                "confidence": m.get("confidence", 1.0),
            }
            for m in mappings
        ]

        stmt = pg_insert(KeywordMappingORM.__table__).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["keyword"],
            set_={
                "tag_id": stmt.excluded.tag_id,
                "is_auto": stmt.excluded.is_auto,
                "confidence": stmt.excluded.confidence,
            },
        )
        await self._session.execute(stmt)
        return len(rows)
