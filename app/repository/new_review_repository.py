"""신규 리뷰 임시 저장소 (content 포함, is_new=false 시 DB 트리거로 자동 삭제)"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from supabase import AsyncClient

from schemas.dto import BranchReviewsDTO

logger = logging.getLogger(__name__)


class NewReviewRepository:
    """new_reviews 테이블 접근"""

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    @property
    def table_name(self) -> str:
        return "new_reviews"

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
                result = await self._client.rpc(
                    "upsert_new_reviews",
                    {"p_reviews": safe_data},
                ).execute()

                count = result.data if isinstance(result.data, int) else len(batch)
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
        query = self._client.table(self.table_name).select("*", count="exact")

        if branch_ids:
            query = query.in_("branch_id", branch_ids)

        if date_from:
            query = query.gte("review_date", date_from)
        if date_to:
            next_day = (
                datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            ).strftime("%Y-%m-%d")
            query = query.lt("review_date", next_day)

        if sort_by == "rating_low":
            query = query.order("rating_service", desc=False, nullsfirst=False)
        else:
            query = query.order("review_date", desc=True)

        query = query.range(offset, offset + limit - 1)
        result = await query.execute()

        # is_new=true 고정 (new_reviews에 있는 리뷰는 모두 신규)
        reviews = [{**r, "is_new": True} for r in (result.data or [])]

        return BranchReviewsDTO(
            reviews=reviews,
            total=result.count or 0,
            car_models=[],
        )
