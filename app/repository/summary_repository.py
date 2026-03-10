from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.timezone import utc_now
from models.summary import Summary
from schemas.dto import SummaryStatsDTO

from .base import BaseRepository
from .orm_models import BranchReviewORM, BranchSummaryHistoryORM, BranchSummaryORM

logger = logging.getLogger(__name__)


ALLOWED_SORT_COLUMNS = {
    "branch_id", "branch_name", "region", "status",
    "review_count", "avg_rating", "updated_at", "created_at",
}


class SummaryRepository(BaseRepository[Summary]):
    """branch_summaries 테이블 Repository"""

    model = Summary
    orm_model = BranchSummaryORM

    @property
    def table_name(self) -> str:
        return "branch_summaries"

    async def get_by_branch_id(self, branch_id: int) -> Summary | None:
        """branch_id로 요약 조회"""
        result = await self._session.execute(
            select(BranchSummaryORM).where(
                BranchSummaryORM.branch_id == branch_id
            )
        )
        row = result.scalar_one_or_none()
        return self._to_pydantic(row) if row else None

    async def get_all_with_filters(
        self,
        region: str | None = None,
        region_group: str | None = None,
        min_reviews: int = 0,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "branch_id",
        order: str = "asc",
    ) -> list[Summary]:
        """필터링된 목록 조회"""
        stmt = select(BranchSummaryORM)

        if min_reviews > 0:
            stmt = stmt.where(BranchSummaryORM.review_count >= min_reviews)
        if region_group:
            from core.constants import REGION_GROUP_PREFIXES

            prefixes = REGION_GROUP_PREFIXES.get(region_group, [])
            if prefixes:
                stmt = stmt.where(
                    or_(*[BranchSummaryORM.region.ilike(f"{p}%") for p in prefixes])
                )
        elif region:
            stmt = stmt.where(BranchSummaryORM.region.ilike(f"%{region}%"))

        if sort_by not in ALLOWED_SORT_COLUMNS:
            sort_by = "branch_id"

        is_desc = order.lower() == "desc"
        sort_col = getattr(BranchSummaryORM, sort_by)

        # NULL 값을 항상 마지막으로 정렬 (NULLS LAST)
        if is_desc:
            stmt = stmt.order_by(sort_col.desc().nulls_last())
        else:
            stmt = stmt.order_by(sort_col.asc().nulls_last())

        stmt = stmt.offset(offset).limit(limit)

        result = await self._session.execute(stmt)
        return [self._to_pydantic(row) for row in result.scalars().all()]

    async def upsert_by_branch_id(self, data: dict) -> Summary | None:
        """branch_id 기준 저장/업데이트"""
        if "branch_id" not in data:
            raise ValueError("branch_id는 필수입니다")

        stmt = pg_insert(BranchSummaryORM.__table__).values(**data)
        update_cols = {k: v for k, v in data.items() if k != "branch_id"}
        stmt = stmt.on_conflict_do_update(
            index_elements=["branch_id"],
            set_=update_cols,
        )
        stmt = stmt.returning(BranchSummaryORM.__table__)

        result = await self._session.execute(stmt)
        row = result.mappings().one_or_none()
        return self.model(**row) if row else None

    async def update_field(self, branch_id: int, field: str, value) -> Summary | None:
        """특정 필드만 업데이트"""
        stmt = (
            update(BranchSummaryORM)
            .where(BranchSummaryORM.branch_id == branch_id)
            .values(**{field: value})
            .returning(BranchSummaryORM.__table__)
        )
        result = await self._session.execute(stmt)
        row = result.mappings().one_or_none()
        return self.model(**row) if row else None

    async def get_stats(self) -> SummaryStatsDTO:
        """통계 조회 (RPC로 DB 서버에서 집계)"""
        result = await self._session.execute(
            text("SELECT * FROM get_summary_stats()")
        )
        row = result.mappings().one_or_none()
        if not row:
            return SummaryStatsDTO(total=0, total_reviews=0)
        return SummaryStatsDTO(
            total=row.get("total_branches", 0),
            total_reviews=row.get("total_reviews", 0),
        )

    async def search(
        self,
        keyword: str | None = None,
        region: str | None = None,
        region_group: str | None = None,
        min_rating: float | None = None,
        max_rating: float | None = None,
        min_reviews: int = 0,
        limit: int = 50,
    ) -> list[Summary]:
        """검색 (DB-side 키워드 필터링)"""
        stmt = select(BranchSummaryORM)

        if min_reviews > 0:
            stmt = stmt.where(BranchSummaryORM.review_count >= min_reviews)
        if region_group:
            from core.constants import REGION_GROUP_PREFIXES

            prefixes = REGION_GROUP_PREFIXES.get(region_group, [])
            if prefixes:
                stmt = stmt.where(
                    or_(*[BranchSummaryORM.region.ilike(f"{p}%") for p in prefixes])
                )
        elif region:
            stmt = stmt.where(BranchSummaryORM.region.ilike(f"%{region}%"))
        if min_rating is not None:
            stmt = stmt.where(BranchSummaryORM.avg_rating >= min_rating)
        if max_rating is not None:
            stmt = stmt.where(BranchSummaryORM.avg_rating <= max_rating)

        if keyword:
            pattern = f"%{keyword}%"
            conditions = [
                BranchSummaryORM.branch_name.ilike(pattern),
                BranchSummaryORM.region.ilike(pattern),
            ]
            if keyword.isdigit():
                conditions.append(BranchSummaryORM.branch_id == int(keyword))
            stmt = stmt.where(or_(*conditions))

        stmt = stmt.order_by(BranchSummaryORM.branch_id).limit(limit)

        result = await self._session.execute(stmt)
        return [self._to_pydantic(row) for row in result.scalars().all()]

    async def delete_by_branch_id(self, branch_id: int) -> bool:
        """branch_id로 삭제"""
        stmt = (
            delete(BranchSummaryORM)
            .where(BranchSummaryORM.branch_id == branch_id)
            .returning(BranchSummaryORM.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_branch_ids_by_date_range(
        self,
        review_date_from: datetime | None = None,
        review_date_to: datetime | None = None,
    ) -> list[int]:
        """해당 기간에 리뷰가 있는 지점 ID 목록 반환"""
        stmt = select(BranchReviewORM.branch_id).distinct()

        if review_date_from:
            stmt = stmt.where(BranchReviewORM.review_date >= review_date_from)
        if review_date_to:
            # 종료일 전체를 포함하기 위해 다음날 00:00:00 미만으로 비교
            next_day = review_date_to + timedelta(days=1)
            stmt = stmt.where(BranchReviewORM.review_date < next_day)

        stmt = stmt.where(BranchReviewORM.branch_id.is_not(None))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_region_data(self) -> list[dict]:
        """지역별 데이터 조회 (region, avg_rating, review_count)"""
        stmt = select(
            BranchSummaryORM.region,
            BranchSummaryORM.avg_rating,
            BranchSummaryORM.review_count,
        )
        result = await self._session.execute(stmt)
        return [dict(row._mapping) for row in result.all()]

    async def get_all_ratings(self) -> list[float]:
        """모든 평점 조회"""
        stmt = select(BranchSummaryORM.avg_rating).where(
            BranchSummaryORM.avg_rating.isnot(None)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ============================================================
    # 히스토리 관련 메서드
    # ============================================================

    async def save_history(
        self,
        branch_id: int,
        summary_all: str | None = None,
        summary_1y: str | None = None,
        summary_6m: str | None = None,
        summary_3m: str | None = None,
        summary_1m: str | None = None,
        keywords: list[str] | None = None,
        review_count: int = 0,
        avg_rating: float | None = None,
        generated_by: str = "scheduler",
    ) -> dict | None:
        """요약 히스토리 저장"""
        try:
            data = {
                "branch_id": branch_id,
                "summary_all": summary_all,
                "summary_1y": summary_1y,
                "summary_6m": summary_6m,
                "summary_3m": summary_3m,
                "summary_1m": summary_1m,
                "keywords": keywords or [],
                "review_count": review_count,
                "avg_rating": avg_rating,
                "generated_by": generated_by,
            }

            stmt = (
                pg_insert(BranchSummaryHistoryORM.__table__)
                .values(**data)
                .returning(BranchSummaryHistoryORM.__table__)
            )
            result = await self._session.execute(stmt)
            row = result.mappings().one_or_none()

            if row:
                logger.info("요약 히스토리 저장: branch_id=%s, by=%s", branch_id, generated_by)
                return dict(row)
            return None
        except Exception as e:
            logger.error("요약 히스토리 저장 실패: %s", e)
            return None

    async def get_history(
        self,
        branch_id: int,
        limit: int = 10,
    ) -> list[dict]:
        """요약 히스토리 조회 (최신순)"""
        try:
            stmt = (
                select(BranchSummaryHistoryORM)
                .where(BranchSummaryHistoryORM.branch_id == branch_id)
                .order_by(BranchSummaryHistoryORM.created_at.desc())
                .limit(limit)
            )
            result = await self._session.execute(stmt)
            return [self._to_dict(row) for row in result.scalars().all()]
        except Exception as e:
            logger.error("요약 히스토리 조회 실패: %s", e)
            return []

    # ============================================================
    # Pending 요약 관련 메서드
    # ============================================================

    async def get_pending_summaries(self, limit: int = 50) -> list[Summary]:
        """pending_summaries가 있는 지점 목록 조회"""
        try:
            # pending_summaries가 빈 객체가 아닌 것만 조회
            stmt = (
                select(BranchSummaryORM)
                .where(BranchSummaryORM.pending_summaries.isnot(None))
                .where(BranchSummaryORM.pending_summaries != {})
                .order_by(BranchSummaryORM.updated_at.desc())
                .limit(limit)
            )
            result = await self._session.execute(stmt)
            return [self._to_pydantic(row) for row in result.scalars().all()]
        except Exception as e:
            logger.error("Pending 요약 조회 실패: %s", e)
            return []

    async def set_pending_summary(
        self,
        branch_id: int,
        pending_data: dict,
    ) -> Summary | None:
        """pending 요약 설정 (승인 대기 상태로)"""
        try:
            stmt = (
                update(BranchSummaryORM)
                .where(BranchSummaryORM.branch_id == branch_id)
                .values(
                    pending_summaries=pending_data,
                    updated_at=utc_now(),
                )
                .returning(BranchSummaryORM.__table__)
            )
            result = await self._session.execute(stmt)
            row = result.mappings().one_or_none()

            if row:
                logger.info("Pending 요약 설정: branch_id=%s", branch_id)
                return self.model(**row)
            return None
        except Exception as e:
            logger.error("Pending 요약 설정 실패: %s", e)
            return None

    async def approve_pending_summary(self, branch_id: int) -> Summary | None:
        """pending 요약 승인 (실제 필드로 이동)"""
        try:
            # 현재 pending_summaries 조회
            current = await self.get_by_branch_id(branch_id)
            if not current or not current.pending_summaries:
                logger.warning("승인할 pending 요약 없음: branch_id=%s", branch_id)
                return None

            pending = current.pending_summaries

            # 히스토리 저장 (승인 전 현재 상태)
            await self.save_history(
                branch_id=branch_id,
                summary_all=current.summary_all,
                summary_1y=current.summary_1y,
                summary_6m=current.summary_6m,
                summary_3m=current.summary_3m,
                summary_1m=current.summary_1m,
                keywords=current.keywords,
                review_count=current.review_count,
                avg_rating=current.avg_rating,
                generated_by="before_approve",
            )

            # pending 데이터로 실제 필드 업데이트
            update_data: dict = {
                "pending_summaries": {},  # pending 초기화
                "updated_at": utc_now(),
            }

            # pending에 있는 필드만 업데이트
            for field in ["summary_all", "summary_1y", "summary_6m", "summary_3m", "summary_1m", "keywords"]:
                if field in pending and pending[field]:
                    update_data[field] = pending[field]

            stmt = (
                update(BranchSummaryORM)
                .where(BranchSummaryORM.branch_id == branch_id)
                .values(**update_data)
                .returning(BranchSummaryORM.__table__)
            )
            result = await self._session.execute(stmt)
            row = result.mappings().one_or_none()

            if row:
                logger.info("Pending 요약 승인 완료: branch_id=%s", branch_id)
                return self.model(**row)
            return None
        except Exception as e:
            logger.error("Pending 요약 승인 실패: %s", e)
            return None

    async def reject_pending_summary(self, branch_id: int) -> Summary | None:
        """pending 요약 거부 (pending 초기화)"""
        try:
            stmt = (
                update(BranchSummaryORM)
                .where(BranchSummaryORM.branch_id == branch_id)
                .values(
                    pending_summaries={},
                    updated_at=utc_now(),
                )
                .returning(BranchSummaryORM.__table__)
            )
            result = await self._session.execute(stmt)
            row = result.mappings().one_or_none()

            if row:
                logger.info("Pending 요약 거부: branch_id=%s", branch_id)
                return self.model(**row)
            return None
        except Exception as e:
            logger.error("Pending 요약 거부 실패: %s", e)
            return None
