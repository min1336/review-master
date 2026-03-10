"""
지점별 태그 Repository (branch_tags 테이블)
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import datetime

from sqlalchemy import func, select, text
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
        """여러 지점의 TOP N 태그 일괄 조회 (TF-IDF 정규화 랭킹)

        TF-IDF 가중치로 정렬하여 모든 업체에 공통인 태그(사고 처리 등)의
        순위를 낮추고 업체별 특색 있는 태그를 상위로 올린다.
        """
        if not branch_ids:
            return {}

        # 쿼리 A: branch_tags JOIN tags — branch_ids 필터 + 태그 이름 동시 조회
        stmt_a = (
            select(
                BranchTagORM.branch_id,
                BranchTagORM.tag_id,
                BranchTagORM.count,
                TagORM.name.label("tag_name"),
            )
            .join(TagORM, BranchTagORM.tag_id == TagORM.id)
            .where(BranchTagORM.branch_id.in_(branch_ids))
            .where(BranchTagORM.period_type == period_type)
            .where(BranchTagORM.count > 0)
        )
        result_a = await self._session.execute(stmt_a)
        rows = result_a.all()

        if not rows:
            return {str(bid): [] for bid in branch_ids}

        # 쿼리 B: IDF 집계 + total_branches 스칼라 서브쿼리 통합
        total_sq = (
            select(func.count(BranchTagORM.branch_id.distinct()))
            .where(BranchTagORM.period_type == period_type)
            .where(BranchTagORM.count > 0)
            .scalar_subquery()
        )
        idf_stmt = (
            select(
                BranchTagORM.tag_id,
                func.count(BranchTagORM.branch_id.distinct()).label("bc"),
                total_sq.label("total_branches"),
            )
            .where(BranchTagORM.period_type == period_type)
            .where(BranchTagORM.count > 0)
            .group_by(BranchTagORM.tag_id)
        )
        idf_result = await self._session.execute(idf_stmt)
        idf_rows = idf_result.all()

        total_branches = idf_rows[0].total_branches if idf_rows else 1
        idf = {
            r.tag_id: math.log(total_branches / max(r.bc, 1)) + 1
            for r in idf_rows
        }

        # 업체별 태그 총합 (TF 정규화용)
        branch_totals: dict[int, int] = defaultdict(int)
        for row in rows:
            branch_totals[row.branch_id] += row.count

        # TF-IDF 스코어 계산 및 정렬
        scored: dict[str, list] = defaultdict(list)
        for row in rows:
            tf = row.count / max(branch_totals[row.branch_id], 1)
            score = tf * idf.get(row.tag_id, 1.0)
            scored[str(row.branch_id)].append(
                {"name": row.tag_name, "count": row.count, "_score": score}
            )

        # 업체별 TF-IDF 순으로 정렬 후 top_n 추출
        result_dict: dict[str, list] = {}
        for bid in branch_ids:
            bid_str = str(bid)
            tags = scored.get(bid_str, [])
            tags.sort(key=lambda t: t["_score"], reverse=True)
            result_dict[bid_str] = [
                {"name": t["name"], "count": t["count"]}
                for t in tags[:top_n]
            ]

        return result_dict

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
