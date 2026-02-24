from __future__ import annotations

import logging
from datetime import datetime, timedelta

from core.timezone import utc_now

from models.summary import Summary
from schemas.dto import SummaryStatsDTO

from .base import BaseRepository

logger = logging.getLogger(__name__)

# 테이블 이름 상수
TABLE_BRANCH_REVIEWS = "branch_reviews"
TABLE_SUMMARIES_HISTORY = "branch_summaries_history"


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
        if region:
            query = query.ilike("region", f"%{region}%")

        is_desc = order.lower() == "desc"
        # avg_rating 정렬 시 NULL을 가장 낮은 점수로 처리 (NULLS LAST)
        if sort_by == "avg_rating":
            query = query.order(sort_by, desc=is_desc, nullsfirst=False)
        else:
            query = query.order(sort_by, desc=is_desc)
        query = query.range(offset, offset + limit - 1)

        result = await query.execute()
        return [self.model(**row) for row in result.data]

    async def upsert_by_branch_id(self, data: dict) -> Summary | None:
        """branch_id 기준 저장/업데이트"""
        if "branch_id" not in data:
            raise ValueError("branch_id는 필수입니다")

        result = (
            await self._client.table(self.table_name)
            .upsert(data, on_conflict="branch_id")
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
        """통계 조회 (RPC로 DB 서버에서 집계)"""
        result = await self._client.rpc("get_summary_stats").execute()
        row = result.data[0] if result.data else {}
        return SummaryStatsDTO(
            total=row.get("total_branches", 0),
            total_reviews=row.get("total_reviews", 0),
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
        """검색 (DB-side 키워드 필터링)"""
        query = self._client.table(self.table_name).select("*")

        if min_reviews > 0:
            query = query.gte("review_count", min_reviews)
        if region:
            query = query.ilike("region", f"%{region}%")
        if min_rating is not None:
            query = query.gte("avg_rating", min_rating)
        if max_rating is not None:
            query = query.lte("avg_rating", max_rating)

        if keyword:
            keyword_pattern = f"%{keyword}%"
            if keyword.isdigit():
                query = query.or_(
                    f"branch_name.ilike.{keyword_pattern},"
                    f"region.ilike.{keyword_pattern},"
                    f"branch_id.eq.{keyword}"
                )
            else:
                query = query.or_(
                    f"branch_name.ilike.{keyword_pattern},"
                    f"region.ilike.{keyword_pattern}"
                )

        result = await query.order("branch_id").limit(limit).execute()
        return [self.model(**row) for row in result.data]

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
            # 종료일 전체를 포함하기 위해 다음날 00:00:00 미만으로 비교
            next_day = review_date_to + timedelta(days=1)
            query = query.lt("review_date", next_day.isoformat())

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
        """
        요약 히스토리 저장

        Args:
            branch_id: 지점 ID
            summary_all ~ summary_1m: 기간별 요약
            keywords: 키워드 목록
            review_count: 리뷰 수
            avg_rating: 평균 평점
            generated_by: 생성 주체 (scheduler, manual, monthly)

        Returns:
            저장된 히스토리 데이터
        """
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

            result = await self._client.table(TABLE_SUMMARIES_HISTORY).insert(data).execute()

            if result.data:
                logger.info(f"요약 히스토리 저장: branch_id={branch_id}, by={generated_by}")
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"요약 히스토리 저장 실패: {e}")
            return None

    async def get_history(
        self,
        branch_id: int,
        limit: int = 10,
    ) -> list[dict]:
        """
        요약 히스토리 조회

        Args:
            branch_id: 지점 ID
            limit: 조회 개수

        Returns:
            히스토리 목록 (최신순)
        """
        try:
            result = await self._client.table(TABLE_SUMMARIES_HISTORY).select(
                "*"
            ).eq(
                "branch_id", branch_id
            ).order(
                "created_at", desc=True
            ).limit(limit).execute()

            return result.data or []
        except Exception as e:
            logger.error(f"요약 히스토리 조회 실패: {e}")
            return []

    # ============================================================
    # Pending 요약 관련 메서드
    # ============================================================

    async def get_pending_summaries(self, limit: int = 50) -> list[Summary]:
        """
        pending_summaries가 있는 지점 목록 조회

        Returns:
            pending 요약이 있는 지점 목록
        """
        try:
            # pending_summaries가 빈 객체가 아닌 것만 조회
            result = await self._client.table(self.table_name).select(
                "*"
            ).neq(
                "pending_summaries", {}
            ).order(
                "updated_at", desc=True
            ).limit(limit).execute()

            return [self.model(**row) for row in result.data] if result.data else []
        except Exception as e:
            logger.error(f"Pending 요약 조회 실패: {e}")
            return []

    async def set_pending_summary(
        self,
        branch_id: int,
        pending_data: dict,
    ) -> Summary | None:
        """
        pending 요약 설정 (승인 대기 상태로)

        Args:
            branch_id: 지점 ID
            pending_data: pending 요약 데이터
                {
                    "summary_all": "...",
                    "summary_1m": "...",
                    "keywords": [...],
                    "generated_at": "2026-02-05T12:00:00",
                    "generated_by": "monthly"
                }

        Returns:
            업데이트된 Summary
        """
        try:
            result = await self._client.table(self.table_name).update({
                "pending_summaries": pending_data,
                "updated_at": utc_now().isoformat(),
            }).eq("branch_id", branch_id).execute()

            if result.data:
                logger.info(f"Pending 요약 설정: branch_id={branch_id}")
                return self.model(**result.data[0])
            return None
        except Exception as e:
            logger.error(f"Pending 요약 설정 실패: {e}")
            return None

    async def approve_pending_summary(self, branch_id: int) -> Summary | None:
        """
        pending 요약 승인 (실제 필드로 이동)

        Args:
            branch_id: 지점 ID

        Returns:
            업데이트된 Summary
        """
        try:
            # 현재 pending_summaries 조회
            current = await self.get_by_branch_id(branch_id)
            if not current or not current.pending_summaries:
                logger.warning(f"승인할 pending 요약 없음: branch_id={branch_id}")
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
            update_data = {
                "pending_summaries": {},  # pending 초기화
                "updated_at": utc_now().isoformat(),
            }

            # pending에 있는 필드만 업데이트
            for field in ["summary_all", "summary_1y", "summary_6m", "summary_3m", "summary_1m", "keywords"]:
                if field in pending and pending[field]:
                    update_data[field] = pending[field]

            result = await self._client.table(self.table_name).update(
                update_data
            ).eq("branch_id", branch_id).execute()

            if result.data:
                logger.info(f"Pending 요약 승인 완료: branch_id={branch_id}")
                return self.model(**result.data[0])
            return None
        except Exception as e:
            logger.error(f"Pending 요약 승인 실패: {e}")
            return None

    async def reject_pending_summary(self, branch_id: int) -> Summary | None:
        """
        pending 요약 거부 (pending 초기화)

        Args:
            branch_id: 지점 ID

        Returns:
            업데이트된 Summary
        """
        try:
            result = await self._client.table(self.table_name).update({
                "pending_summaries": {},
                "updated_at": utc_now().isoformat(),
            }).eq("branch_id", branch_id).execute()

            if result.data:
                logger.info(f"Pending 요약 거부: branch_id={branch_id}")
                return self.model(**result.data[0])
            return None
        except Exception as e:
            logger.error(f"Pending 요약 거부 실패: {e}")
            return None
