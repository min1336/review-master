from __future__ import annotations

import logging

from models.review_read_status import ReviewReadStatus

from .base import BaseRepository
from .session import execute_with_retry

logger = logging.getLogger(__name__)


class ReviewReadStatusRepository(BaseRepository[ReviewReadStatus]):
    """review_read_status 테이블 Repository"""

    model = ReviewReadStatus

    @property
    def table_name(self) -> str:
        return "review_read_status"

    async def mark_as_read(
        self, review_ids: list[str], read_by: str | None = None
    ) -> int:
        """
        리뷰 읽음 처리

        Args:
            review_ids: 읽음 처리할 리뷰 ID 목록
            read_by: 읽은 사용자 (선택)

        Returns:
            int: 처리된 리뷰 개수
        """
        if not review_ids:
            return 0

        success_count = 0
        batch_size = 100

        # 배치 처리
        for i in range(0, len(review_ids), batch_size):
            batch = review_ids[i : i + batch_size]
            try:
                insert_data = [
                    {
                        "review_id": rid,
                        "read_by": read_by,
                    }
                    for rid in batch
                ]

                # upsert로 중복 방지
                await (
                    self._client.table(self.table_name)
                    .upsert(insert_data, on_conflict="review_id")
                    .execute()
                )
                success_count += len(batch)
            except Exception as e:
                logger.warning(f"Failed to mark reviews as read: {e}")

        return success_count

    async def mark_all_as_read(self, read_by: str | None = None) -> int:
        """
        모든 리뷰 읽음 처리 (branch_reviews 테이블 기준)

        Args:
            read_by: 읽은 사용자 (선택)

        Returns:
            int: 처리된 리뷰 개수
        """
        try:
            # branch_reviews에서 모든 review_id 조회
            result = await execute_with_retry(
                self._client.table("branch_reviews")
                .select("review_id")
                .not_.is_("review_id", "null")
            )

            if not result.data:
                return 0

            review_ids = [r["review_id"] for r in result.data if r.get("review_id")]
            return await self.mark_as_read(review_ids, read_by)
        except Exception as e:
            logger.error(f"Failed to mark all reviews as read: {e}")
            return 0

    async def get_read_ids(self, review_ids: list[str]) -> set[str]:
        """
        읽은 리뷰 ID 목록 조회

        Args:
            review_ids: 확인할 리뷰 ID 목록

        Returns:
            set[str]: 읽은 리뷰 ID 목록
        """
        if not review_ids:
            return set()

        try:
            result = await execute_with_retry(
                self._client.table(self.table_name)
                .select("review_id")
                .in_("review_id", review_ids)
            )

            return {r["review_id"] for r in result.data if r.get("review_id")}
        except Exception as e:
            logger.warning(f"Failed to get read ids: {e}")
            return set()

    async def is_read(self, review_id: str) -> bool:
        """
        리뷰 읽음 여부 확인

        Args:
            review_id: 리뷰 ID

        Returns:
            bool: 읽음 여부
        """
        try:
            result = await execute_with_retry(
                self._client.table(self.table_name)
                .select("id")
                .eq("review_id", review_id)
                .limit(1)
            )

            return len(result.data) > 0 if result.data else False
        except Exception as e:
            logger.warning(f"Failed to check read status: {e}")
            return False

    async def unmark_as_read(self, review_ids: list[str]) -> int:
        """
        리뷰 읽음 해제

        Args:
            review_ids: 읽음 해제할 리뷰 ID 목록

        Returns:
            int: 처리된 리뷰 개수
        """
        if not review_ids:
            return 0

        try:
            result = await execute_with_retry(
                self._client.table(self.table_name)
                .delete()
                .in_("review_id", review_ids)
            )

            return len(result.data) if result.data else 0
        except Exception as e:
            logger.warning(f"Failed to unmark reviews as read: {e}")
            return 0

    async def get_read_count(self) -> int:
        """
        읽은 리뷰 총 개수 조회

        Returns:
            int: 읽은 리뷰 개수
        """
        try:
            result = await execute_with_retry(
                self._client.table(self.table_name).select("id", count="exact").limit(1)
            )

            return result.count or 0
        except Exception as e:
            logger.warning(f"Failed to get read count: {e}")
            return 0
