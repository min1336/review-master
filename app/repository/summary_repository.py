"""
지점 요약 Repository (branch_summaries 테이블)

이 모듈은 지점 요약 데이터에 대한 CRUD 작업을 담당합니다.
- 요약 목록 조회 (필터링, 정렬, 페이징)
- 날짜 범위로 지점 ID 조회
- 통계 조회
"""

from __future__ import annotations

from datetime import datetime

from models.summary import Summary
from schemas.dto import SummaryStatsDTO

from .base import BaseRepository

# 테이블 이름 상수
TABLE_BRANCH_REVIEWS = "branch_reviews"


class SummaryRepository(BaseRepository[Summary]):
    """branch_summaries 테이블 Repository"""

    model = Summary

    @property
    def table_name(self) -> str:
        return "branch_summaries"

    async def get_by_branch_id(self, branch_id: int) -> Summary | None:
        """branch_id로 요약 조회"""
        result = (
            await self._client.table(self.table_name)
            .select("*")
            .eq("branch_id", branch_id)
            .execute()
        )
        return self.model(**result.data[0]) if result.data else None

    async def get_all_with_filters(
        self,
        status: str | None = None,
        region: str | None = None,
        min_reviews: int = 0,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "branch_id",
        order: str = "asc",
    ) -> list[Summary]:
        """필터링된 목록 조회"""
        query = self._client.table(self.table_name).select("*")

        if min_reviews > 0:
            query = query.gte("review_count", min_reviews)
        if status:
            query = query.eq("status", status)
        if region:
            query = query.ilike("region", f"%{region}%")

        is_desc = order.lower() == "desc"
        query = query.order(sort_by, desc=is_desc)
        query = query.range(offset, offset + limit - 1)

        result = await query.execute()
        return [self.model(**row) for row in result.data]

    async def upsert_by_branch_id(self, data: dict) -> Summary | None:
        """branch_id 기준 저장/업데이트"""
        if "branch_id" not in data:
            raise ValueError("branch_id는 필수입니다")

        existing = (
            await self._client.table(self.table_name)
            .select("status")
            .eq("branch_id", data["branch_id"])
            .execute()
        )

        if "status" not in data and not existing.data:
            data["status"] = "draft"

        result = (
            await self._client.table(self.table_name)
            .upsert(data, on_conflict="branch_id")
            .execute()
        )

        return self.model(**result.data[0]) if result.data else None

    async def update_status(self, branch_id: int, status: str) -> Summary | None:
        """상태 변경"""
        result = (
            await self._client.table(self.table_name)
            .update({"status": status})
            .eq("branch_id", branch_id)
            .execute()
        )
        return self.model(**result.data[0]) if result.data else None

    async def update_field(self, branch_id: int, field: str, value) -> Summary | None:
        """특정 필드만 업데이트"""
        result = (
            await self._client.table(self.table_name)
            .update({field: value})
            .eq("branch_id", branch_id)
            .execute()
        )
        return self.model(**result.data[0]) if result.data else None

    async def get_stats(self) -> SummaryStatsDTO:
        """통계 조회"""
        total = (
            await self._client.table(self.table_name)
            .select("id", count="exact")
            .execute()
        )
        draft = (
            await self._client.table(self.table_name)
            .select("id", count="exact")
            .eq("status", "draft")
            .execute()
        )
        approved = (
            await self._client.table(self.table_name)
            .select("id", count="exact")
            .eq("status", "approved")
            .execute()
        )
        published = (
            await self._client.table(self.table_name)
            .select("id", count="exact")
            .eq("status", "published")
            .execute()
        )

        # 총 리뷰 수 계산
        total_reviews = 0
        offset = 0
        page_size = 1000
        while True:
            reviews = (
                await self._client.table(self.table_name)
                .select("review_count")
                .range(offset, offset + page_size - 1)
                .execute()
            )
            if not reviews.data:
                break
            total_reviews += sum(r.get("review_count", 0) or 0 for r in reviews.data)
            if len(reviews.data) < page_size:
                break
            offset += page_size

        return SummaryStatsDTO(
            total=total.count or 0,
            draft=draft.count or 0,
            approved=approved.count or 0,
            published=published.count or 0,
            total_reviews=total_reviews,
        )

    async def search(
        self,
        keyword: str | None = None,
        region: str | None = None,
        min_rating: float | None = None,
        max_rating: float | None = None,
        min_reviews: int = 0,
        limit: int = 50,
    ) -> list[Summary]:
        """검색"""
        query = self._client.table(self.table_name).select("*")

        if min_reviews > 0:
            query = query.gte("review_count", min_reviews)
        if region:
            query = query.ilike("region", f"%{region}%")
        if min_rating is not None:
            query = query.gte("avg_rating", min_rating)
        if max_rating is not None:
            query = query.lte("avg_rating", max_rating)

        result = await query.order("branch_id").limit(limit).execute()
        data = result.data

        # 키워드 필터링 (in-memory)
        if keyword and data:
            keyword_lower = keyword.lower()
            data = [
                row
                for row in data
                if keyword_lower in (row.get("branch_name") or "").lower()
                or keyword_lower in (row.get("keyword_1") or "").lower()
                or keyword_lower in (row.get("keyword_2") or "").lower()
                or keyword_lower in (row.get("keyword_3") or "").lower()
            ]

        return [self.model(**row) for row in data]

    async def delete_by_branch_id(self, branch_id: int) -> bool:
        """branch_id로 삭제"""
        result = (
            await self._client.table(self.table_name)
            .delete()
            .eq("branch_id", branch_id)
            .execute()
        )
        return len(result.data) > 0 if result.data else False

    async def get_branch_ids_by_date_range(
        self,
        review_date_from: datetime | None = None,
        review_date_to: datetime | None = None,
    ) -> list[int]:
        """
        해당 기간에 리뷰가 있는 지점 ID 목록 반환

        Args:
            review_date_from: 시작일 (이 날짜 이후 리뷰)
            review_date_to: 종료일 (이 날짜 이전 리뷰)

        Returns:
            List[int]: branch_id 목록 (예: [101, 205, 312, ...])
                       해당 기간에 리뷰가 1개 이상 있는 지점들

        Note:
            - TABLE_BRANCH_REVIEWS 테이블에서 조회
            - 중복 제거하여 반환
        """
        query = self._client.table(TABLE_BRANCH_REVIEWS).select("branch_id")

        if review_date_from:
            query = query.gte("review_date", review_date_from.isoformat())
        if review_date_to:
            query = query.lte("review_date", review_date_to.isoformat())

        result = await query.execute()

        # 중복 제거하여 반환
        return list({r["branch_id"] for r in result.data if r.get("branch_id")})

    async def get_region_data(self) -> list[dict]:
        """지역별 데이터 조회 (region, avg_rating, review_count)"""
        result = (
            await self._client.table(self.table_name)
            .select("region, avg_rating, review_count")
            .execute()
        )
        return result.data if result.data else []

    async def get_all_ratings(self) -> list[float]:
        """모든 평점 조회"""
        result = (
            await self._client.table(self.table_name)
            .select("avg_rating")
            .execute()
        )
        return [r["avg_rating"] for r in result.data if r.get("avg_rating")]
