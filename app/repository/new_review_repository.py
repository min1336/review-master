"""신규 리뷰 임시 저장소 (content 포함, is_new=false 시 DB 트리거로 자동 삭제)"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.dto import BranchReviewsDTO

from .orm_models import NewReviewORM

logger = logging.getLogger(__name__)


class NewReviewRepository:
    """new_reviews 테이블 접근"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_batch(self, reviews: list[dict], batch_size: int = 100) -> int:
        """신규 리뷰 일괄 저장 (content 포함)"""
        success_count = 0
        total = len(reviews)

        for i in range(0, total, batch_size):
            batch = reviews[i : i + batch_size]
            try:
                insert_data = []
                for r in batch:
                    rating_svc = r.get("rating_service") or r.get(
                        "지점평점(친절/편의성)"
                    )
                    rating_conv = r.get("rating_convenience") or r.get(
                        "인수/반납편의성"
                    )
                    data = {
                        "review_id": r.get("review_id") or r.get("리뷰번호"),
                        "branch_id": r.get("branch_id") or r.get("지점번호"),
                        "branch_name": r.get("branch_name") or r.get("예약_지점명"),
                        "company_name": r.get("company_name") or r.get("예약_업체명"),
                        "content": r.get("content") or r.get("리뷰내용"),
                        "rating_service": rating_svc,
                        "rating_car": r.get("rating_car") or r.get("차량평점"),
                        "rating_convenience": rating_conv,
                        "review_date": r.get("review_date") or r.get("등록일시"),
                        "car_model": r.get("car_model") or r.get("차량모델"),
                        "rent_type": r.get("rent_type") or r.get("렌트타입"),
                    }
                    insert_data.append(data)

                safe_data = json.loads(json.dumps(insert_data, default=str))
                result = await self._session.execute(
                    text("SELECT upsert_new_reviews(:p_reviews::jsonb)"),
                    {"p_reviews": json.dumps(safe_data)},
                )

                row = result.scalar_one_or_none()
                count = row if isinstance(row, int) else len(batch)
                success_count += count
            except Exception as e:
                logger.warning(f"Failed to upsert new reviews batch: {e}")

        return success_count

    async def search_with_filters(
        self,
        branch_ids: list[int] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        sort_by: str = "latest",
        limit: int = 20,
        offset: int = 0,
    ) -> BranchReviewsDTO:
        """신규 리뷰 검색 (content 포함)"""
        conditions = []

        if branch_ids:
            conditions.append(NewReviewORM.branch_id.in_(branch_ids))
        if date_from:
            conditions.append(NewReviewORM.review_date >= date_from)
        if date_to:
            next_day = (
                datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            ).strftime("%Y-%m-%d")
            conditions.append(NewReviewORM.review_date < next_day)

        # 총 개수 조회
        count_stmt = select(func.count()).select_from(NewReviewORM)
        for cond in conditions:
            count_stmt = count_stmt.where(cond)
        count_result = await self._session.execute(count_stmt)
        total_count = count_result.scalar_one()

        # 데이터 조회
        data_stmt = select(NewReviewORM)
        for cond in conditions:
            data_stmt = data_stmt.where(cond)

        if sort_by == "rating_low":
            data_stmt = data_stmt.order_by(
                NewReviewORM.rating_service.asc().nullslast()
            )
        else:
            data_stmt = data_stmt.order_by(NewReviewORM.review_date.desc())

        data_stmt = data_stmt.offset(offset).limit(limit)
        data_result = await self._session.execute(data_stmt)
        rows = data_result.scalars().all()

        # ORM → dict 변환, is_new=True 고정
        reviews = []
        for row in rows:
            d = {c.key: getattr(row, c.key) for c in row.__table__.columns}
            d["is_new"] = True
            reviews.append(d)

        return BranchReviewsDTO(
            reviews=reviews,
            total=total_count,
            car_models=[],
        )
