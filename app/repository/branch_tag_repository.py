"""
지점별 태그 Repository (branch_tags 테이블)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload

from models.tag import BranchTag

from .base import BaseRepository
from .orm_models import BranchTagORM, TagORM

logger = logging.getLogger(__name__)


class BranchTagRepository(BaseRepository[BranchTag]):
    """branch_tags 테이블 Repository"""

    model = BranchTag
    orm_model = BranchTagORM

    @property
    def table_name(self) -> str:
        return "branch_tags"

    async def get_by_branch(
        self, branch_id: int, period_type: str = "all", limit: int = 10
    ) -> list[BranchTag]:
        """지점별 태그 조회"""
        stmt = (
            select(BranchTagORM)
            .options(
                selectinload(BranchTagORM.tag).selectinload(TagORM.category)
            )
            .where(BranchTagORM.branch_id == branch_id)
            .where(BranchTagORM.period_type == period_type)
            .order_by(BranchTagORM.count.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()

        branch_tags = []
        for row in rows:
            data = {c.key: getattr(row, c.key) for c in row.__table__.columns}
            if row.tag:
                tag_data = {
                    c.key: getattr(row.tag, c.key)
                    for c in row.tag.__table__.columns
                }
                if row.tag.category:
                    tag_data["categories"] = {
                        c.key: getattr(row.tag.category, c.key)
                        for c in row.tag.category.__table__.columns
                    }
                data["tags"] = tag_data
            branch_tags.append(BranchTag(**data))

        return branch_tags

    async def get_batch_top_tags(
        self, branch_ids: list[int], period_type: str = "all", top_n: int = 3
    ) -> dict:
        """여러 지점의 TOP N 태그 일괄 조회"""
        if not branch_ids:
            return {}

        # 태그 이름 조회
        tags_result = await self._session.execute(
            select(TagORM.id, TagORM.name)
        )
        tag_names = {row.id: row.name for row in tags_result.all()}

        # 지점별 태그 조회
        stmt = (
            select(
                BranchTagORM.branch_id,
                BranchTagORM.tag_id,
                BranchTagORM.count,
            )
            .where(BranchTagORM.branch_id.in_(branch_ids))
            .where(BranchTagORM.period_type == period_type)
            .order_by(BranchTagORM.count.desc())
        )
        result = await self._session.execute(stmt)

        # 지점별 그룹화
        branch_tags: dict[str, list] = defaultdict(list)
        for row in result.all():
            bid = str(row.branch_id)
            if len(branch_tags[bid]) < top_n:
                branch_tags[bid].append(
                    {"name": tag_names.get(row.tag_id, "unknown"), "count": row.count}
                )

        return {str(bid): branch_tags.get(str(bid), []) for bid in branch_ids}

    async def upsert_branch_tags(
        self, branch_id: int, period_type: str, tags_data: list[dict]
    ) -> int:
        """지점별 태그 집계 저장"""
        if not tags_data:
            return 0

        rows = [
            {
                "branch_id": branch_id,
                "tag_id": tag["tag_id"],
                "period_type": period_type,
                "count": tag.get("count", 0),
                "weighted_score": tag.get("weighted_score", 0),
                "rank": tag.get("rank"),
            }
            for tag in tags_data
        ]

        stmt = pg_insert(BranchTagORM.__table__).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["branch_id", "tag_id", "period_type"],
            set_={
                "count": stmt.excluded.count,
                "weighted_score": stmt.excluded.weighted_score,
                "rank": stmt.excluded.rank,
            },
        )
        await self._session.execute(stmt)
        return len(rows)

    async def get_tag_stats_by_period(
        self, branch_id: int, start_date: datetime, end_date: datetime,
    ) -> list[dict]:
        """기간별 태그 감정 통계 (review_tag_mappings RPC)"""
        result = await self._session.execute(
            text('SELECT * FROM "getTagStatsByPeriod"(:branchId, :startDate, :endDate)'),
            {
                "branchId": branch_id,
                "startDate": start_date.strftime("%Y-%m-%d %H:%M:%S"),
                "endDate": end_date.strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
        return [dict(row) for row in result.mappings().all()]
