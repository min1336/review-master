"""
지점별 태그 Repository (branch_tags 테이블)
"""

from __future__ import annotations

import logging
from collections import defaultdict

from models.tag import BranchTag

from .base import BaseRepository

logger = logging.getLogger(__name__)

# 테이블 이름 상수
TABLE_TAGS = "tags"


class BranchTagRepository(BaseRepository[BranchTag]):
    """branch_tags 테이블 Repository"""

    model = BranchTag

    @property
    def table_name(self) -> str:
        return "branch_tags"

    async def get_by_branch(
        self, branch_id: int, period_type: str = "all", limit: int = 10
    ) -> list[BranchTag]:
        """지점별 태그 조회"""
        result = (
            await self._client.table(self.table_name)
            .select("*, tags(id, name, sentiment, categories(id, name, color))")
            .eq("branch_id", branch_id)
            .eq("period_type", period_type)
            .order("count", desc=True)
            .limit(limit)
            .execute()
        )
        return [self.model(**row) for row in result.data]

    async def get_batch_top_tags(
        self, branch_ids: list[int], period_type: str = "positive", top_n: int = 3
    ) -> dict:
        """여러 지점의 TOP N 태그 일괄 조회"""
        if not branch_ids:
            return {}

        # 태그 이름 조회
        tags_result = await self._client.table(TABLE_TAGS).select("id, name").execute()
        tag_names = {t["id"]: t["name"] for t in tags_result.data}

        # 지점별 태그 조회
        result = (
            await self._client.table(self.table_name)
            .select("branch_id, tag_id, count")
            .in_("branch_id", branch_ids)
            .eq("period_type", period_type)
            .order("count", desc=True)
            .execute()
        )

        # 지점별 그룹화
        branch_tags = defaultdict(list)
        for t in result.data:
            bid = str(t["branch_id"])
            if len(branch_tags[bid]) < top_n:
                branch_tags[bid].append(
                    {"name": tag_names.get(t["tag_id"], "unknown"), "count": t["count"]}
                )

        return {str(bid): branch_tags.get(str(bid), []) for bid in branch_ids}

    async def upsert_branch_tags(
        self, branch_id: int, period_type: str, tags_data: list[dict]
    ) -> int:
        """지점별 태그 집계 저장"""
        success_count = 0
        for tag in tags_data:
            try:
                await (
                    self._client.table(self.table_name)
                    .upsert(
                        {
                            "branch_id": branch_id,
                            "tag_id": tag["tag_id"],
                            "period_type": period_type,
                            "count": tag.get("count", 0),
                            "weighted_score": tag.get("weighted_score", 0),
                            "rank": tag.get("rank"),
                        },
                        on_conflict="branch_id,tag_id,period_type",
                    )
                    .execute()
                )
                success_count += 1
            except Exception as e:
                tag_id = tag.get("tag_id")
                logger.warning(
                    f"Failed to upsert branch tag for branch {branch_id}, "
                    f"tag {tag_id}: {e}"
                )
        return success_count
