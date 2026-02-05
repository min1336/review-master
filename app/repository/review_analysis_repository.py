"""review_analysis 테이블 Repository"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from models.review_analysis import ReviewAnalysis
from repository.base import BaseRepository
from supabase import AsyncClient

logger = logging.getLogger(__name__)


@dataclass
class NewReviewListResult:
    """신규 리뷰 목록 결과"""

    reviews: list[dict]
    total: int


class ReviewAnalysisRepository(BaseRepository[ReviewAnalysis]):
    """review_analysis 테이블 Repository"""

    model = ReviewAnalysis

    @property
    def table_name(self) -> str:
        return "review_analysis"

    def __init__(self, client: AsyncClient):
        super().__init__(client)

    async def get_by_review_id(self, review_id: int) -> ReviewAnalysis | None:
        """review_id로 조회"""
        try:
            result = (
                await self._client.table(self.table_name)
                .select("*")
                .eq("review_id", review_id)
                .single()
                .execute()
            )
            return self.model(**result.data) if result.data else None
        except Exception:
            return None

    async def get_new_reviews(
        self,
        branch_id: int | None = None,
        limit: int = 5,
        offset: int = 0,
    ) -> NewReviewListResult:
        """
        신규 리뷰 조회 (is_new=true)

        Args:
            branch_id: 지점 ID (None이면 전체)
            limit: 조회 개수
            offset: 페이징 오프셋

        Returns:
            NewReviewListResult: 리뷰 목록과 총 개수
        """
        try:
            # 쿼리 빌더 시작
            query = (
                self._client.table(self.table_name)
                .select("*", count="exact")
                .eq("is_new", True)
                .eq("is_deleted", False)
            )

            if branch_id is not None:
                query = query.eq("branch_id", branch_id)

            # 정렬 및 페이징
            result = (
                await query.order("review_date", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
            )

            return NewReviewListResult(
                reviews=result.data or [],
                total=result.count or 0,
            )

        except Exception as e:
            logger.error(f"Failed to get new reviews: {e}")
            return NewReviewListResult(reviews=[], total=0)

    async def get_new_review_count(self, branch_id: int | None = None) -> int:
        """신규 리뷰 수 조회"""
        try:
            query = (
                self._client.table(self.table_name)
                .select("review_id", count="exact")
                .eq("is_new", True)
                .eq("is_deleted", False)
            )

            if branch_id is not None:
                query = query.eq("branch_id", branch_id)

            result = await query.execute()
            return result.count or 0

        except Exception as e:
            logger.error(f"Failed to get new review count: {e}")
            return 0

    async def mark_as_read(self, review_ids: list[int] | None = None) -> int:
        """
        읽음 처리 (is_new를 false로 변경)

        Args:
            review_ids: 리뷰 ID 목록 (None이면 전체)

        Returns:
            변경된 레코드 수
        """
        try:
            update_data = {
                "is_new": False,
                "updated_at": datetime.now().isoformat(),
            }

            if review_ids is None:
                # 전체 읽음 처리
                result = (
                    await self._client.table(self.table_name)
                    .update(update_data)
                    .eq("is_new", True)
                    .eq("is_deleted", False)
                    .execute()
                )
            else:
                # 특정 리뷰만 읽음 처리
                result = (
                    await self._client.table(self.table_name)
                    .update(update_data)
                    .in_("review_id", review_ids)
                    .eq("is_new", True)
                    .eq("is_deleted", False)
                    .execute()
                )

            return len(result.data) if result.data else 0

        except Exception as e:
            logger.error(f"Failed to mark reviews as read: {e}")
            return 0

    async def upsert_review(self, data: dict) -> ReviewAnalysis | None:
        """
        리뷰 저장/업데이트 (review_id 기준)

        Args:
            data: 리뷰 데이터 (review_id 필수)

        Returns:
            저장된 ReviewAnalysis 또는 None
        """
        try:
            # updated_at 갱신
            data["updated_at"] = datetime.now().isoformat()

            result = (
                await self._client.table(self.table_name)
                .upsert(data, on_conflict="review_id")
                .execute()
            )

            return self.model(**result.data[0]) if result.data else None

        except Exception as e:
            logger.error(f"Failed to upsert review: {e}")
            return None

    async def soft_delete(self, review_ids: list[int]) -> int:
        """
        soft delete 처리

        Args:
            review_ids: 삭제할 리뷰 ID 목록

        Returns:
            삭제된 레코드 수
        """
        try:
            result = (
                await self._client.table(self.table_name)
                .update({
                    "is_deleted": True,
                    "updated_at": datetime.now().isoformat(),
                })
                .in_("review_id", review_ids)
                .execute()
            )

            return len(result.data) if result.data else 0

        except Exception as e:
            logger.error(f"Failed to soft delete reviews: {e}")
            return 0
