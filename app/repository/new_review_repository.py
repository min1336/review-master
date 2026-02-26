"""신규 리뷰 조회 — branch_reviews 테이블의 is_new=true 행을 조회"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.dto import BranchReviewsDTO

from .orm_models import BranchReviewORM

logger = logging.getLogger(__name__)


class NewReviewRepository:
    """신규 리뷰 조회 (branch_reviews WHERE is_new = true)"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search_with_filters(
        self,
        branch_ids: list[int] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        sort_by: str = "latest",
        limit: int = 20,
        offset: int = 0,
    ) -> BranchReviewsDTO:
        """신규 리뷰 검색 (branch_reviews에서 is_new=true 조회)"""
        conditions = [BranchReviewORM.is_new == True]  # noqa: E712

        if branch_ids is not None:
            conditions.append(BranchReviewORM.branch_id.in_(branch_ids))
        if date_from:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            conditions.append(BranchReviewORM.review_date >= dt_from)
        if date_to:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            conditions.append(BranchReviewORM.review_date < dt_to)

        # 총 개수 조회
        count_stmt = select(func.count()).select_from(BranchReviewORM)
        for cond in conditions:
            count_stmt = count_stmt.where(cond)
        count_result = await self._session.execute(count_stmt)
        total_count = count_result.scalar_one()

        # 데이터 조회
        data_stmt = select(BranchReviewORM)
        for cond in conditions:
            data_stmt = data_stmt.where(cond)

        if sort_by == "rating_low":
            data_stmt = data_stmt.order_by(
                BranchReviewORM.rating_service.asc().nullslast()
            )
        else:
            data_stmt = data_stmt.order_by(BranchReviewORM.review_date.desc())

        data_stmt = data_stmt.offset(offset).limit(limit)
        data_result = await self._session.execute(data_stmt)
        rows = data_result.scalars().all()

        # ORM → dict 변환
        reviews = []
        for row in rows:
            d = {c.key: getattr(row, c.key) for c in row.__table__.columns}
            reviews.append(d)

        return BranchReviewsDTO(
            reviews=reviews,
            total=total_count,
            car_models=[],
        )
