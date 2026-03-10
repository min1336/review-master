"""Step 6: 키워드 누적 관리 (branch_keywords 테이블)"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.timezone import utc_now
from repository.orm_models import BranchKeywordORM
from schemas.dto import ProcessedReviewDTO

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _ensure_aware(dt: datetime | None) -> datetime | None:
    """naive datetime을 UTC aware로 변환"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class KeywordManager:
    """지점별 키워드 누적 집계 및 branch_keywords 테이블 갱신"""

    async def update(
        self, session: AsyncSession, processed: list[ProcessedReviewDTO]
    ) -> int:
        """
        키워드 누적 업데이트

        Args:
            session: AsyncSession
            processed: 처리된 리뷰 목록

        Returns:
            업데이트된 지점 수
        """
        if not processed:
            return 0

        # 1. 지점별 키워드 그룹화 (키워드 -> {count, last_seen_at})
        branch_keywords: dict[int, dict[str, dict]] = defaultdict(dict)

        for pr in processed:
            branch_id = pr.branch_id
            review_date = _ensure_aware(pr.review.created_at) or utc_now()

            for keyword in pr.keywords:
                existing = branch_keywords[branch_id].get(keyword)
                if existing is None:
                    branch_keywords[branch_id][keyword] = {
                        "count": 1,
                        "last_seen_at": review_date,
                    }
                else:
                    existing["count"] += 1
                    if review_date > existing["last_seen_at"]:
                        existing["last_seen_at"] = review_date

        if not branch_keywords:
            logger.info("키워드 업데이트할 데이터 없음")
            return 0

        # 2. 지점별 키워드 업데이트 (처리 후 즉시 메모리 해제)
        updated_branches = 0
        branch_ids = list(branch_keywords.keys())

        for branch_id in branch_ids:
            keywords_data = branch_keywords.pop(branch_id)
            try:
                updated_branches += await self._update_branch(
                    session, branch_id, keywords_data
                )
            except Exception as e:
                logger.warning("지점 %s 키워드 업데이트 실패: %s", branch_id, e)
                continue

        logger.info("총 %s개 지점 키워드 업데이트 완료", updated_branches)
        return updated_branches

    async def _update_branch(
        self,
        session: AsyncSession,
        branch_id: int,
        keywords_data: dict[str, dict],
    ) -> int:
        """단일 지점의 키워드 업데이트.

        Returns:
            1 if updated, 0 otherwise
        """
        # 1. 기존 키워드 로드
        result = await session.execute(
            select(
                BranchKeywordORM.keyword,
                BranchKeywordORM.count,
                BranchKeywordORM.last_seen_at,
            ).where(BranchKeywordORM.branch_id == branch_id)
        )

        existing_map: dict[str, dict] = {
            row.keyword: {
                "count": row.count or 0,
                "last_seen_at": _ensure_aware(row.last_seen_at),
            }
            for row in result.all()
        }

        # 2. 누적 집계 (배치 내 등장 횟수 합산)
        upsert_rows = []
        for keyword, batch_data in keywords_data.items():
            existing = existing_map.get(keyword)
            batch_count = batch_data["count"]
            new_date = batch_data["last_seen_at"]

            if existing:
                new_count = existing["count"] + batch_count
                old_date = existing["last_seen_at"]
                if old_date and new_date:
                    final_date = max(new_date, old_date)
                else:
                    final_date = new_date or old_date
            else:
                new_count = batch_count
                final_date = new_date

            upsert_rows.append({
                "branch_id": branch_id,
                "keyword": keyword,
                "count": new_count,
                "last_seen_at": final_date,
            })

        # 3. 배치 upsert (N개 키워드를 1번의 SQL로 처리)
        if upsert_rows:
            stmt = pg_insert(BranchKeywordORM.__table__).values(upsert_rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["branch_id", "keyword"],
                set_={
                    "count": stmt.excluded.count,
                    "last_seen_at": stmt.excluded.last_seen_at,
                },
            )
            await session.execute(stmt)
            logger.info(
                f"지점 {branch_id} 키워드 {len(upsert_rows)}개 업데이트"
            )
            return 1

        return 0
