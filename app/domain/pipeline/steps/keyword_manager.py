"""Step 6: 키워드 누적 관리 (branch_keywords 테이블)"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime

from core.timezone import utc_now
from typing import TYPE_CHECKING

from schemas.dto import ProcessedReviewDTO

if TYPE_CHECKING:
    from supabase import AsyncClient

logger = logging.getLogger(__name__)


class KeywordManager:
    """지점별 키워드 누적 집계 및 branch_keywords 테이블 갱신"""

    async def update(
        self, client: AsyncClient, processed: list[ProcessedReviewDTO]
    ) -> int:
        """
        키워드 누적 업데이트

        Args:
            client: Supabase AsyncClient
            processed: 처리된 리뷰 목록

        Returns:
            업데이트된 지점 수
        """
        if not processed:
            return 0

        # 1. 지점별 키워드 그룹화 (키워드 → {count, last_seen_at})
        branch_keywords: dict[int, dict[str, dict]] = defaultdict(dict)

        for pr in processed:
            branch_id = pr.branch_id
            review_date = (
                pr.review.created_at.isoformat()
                if pr.review.created_at
                else utc_now().isoformat()
            )

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

        # 2. 지점별 키워드 업데이트
        updated_branches = 0

        for branch_id, keywords_data in branch_keywords.items():
            try:
                # 2-1. 기존 키워드 로드
                existing_data = await (
                    client.table("branch_keywords")
                    .select("keyword, count, last_seen_at")
                    .eq("branch_id", branch_id)
                    .execute()
                )

                existing_map: dict[str, dict] = {}
                if existing_data.data:
                    for row in existing_data.data:
                        # DB에서 돌아온 last_seen_at을 문자열로 통일
                        raw_date = row.get("last_seen_at")
                        if hasattr(raw_date, "isoformat"):
                            raw_date = raw_date.isoformat()
                        existing_map[row["keyword"]] = {
                            "count": row.get("count", 0),
                            "last_seen_at": raw_date,
                        }

                # 2-2. 누적 집계 (배치 내 등장 횟수 합산)
                upsert_rows = []
                for keyword, batch_data in keywords_data.items():
                    existing = existing_map.get(keyword)
                    batch_count = batch_data["count"]
                    new_date = batch_data["last_seen_at"]

                    if existing:
                        new_count = existing["count"] + batch_count
                        old_date = existing["last_seen_at"] or ""
                        final_date = (
                            new_date if new_date > old_date else old_date
                        )
                    else:
                        new_count = batch_count
                        final_date = new_date

                    upsert_rows.append({
                        "branch_id": branch_id,
                        "keyword": keyword,
                        "count": new_count,
                        "last_seen_at": final_date,
                    })

                # 2-3. DB upsert
                if upsert_rows:
                    await (
                        client.table("branch_keywords")
                        .upsert(
                            upsert_rows,
                            on_conflict="branch_id,keyword",
                        )
                        .execute()
                    )
                    updated_branches += 1
                    logger.info(
                        f"지점 {branch_id} 키워드 {len(upsert_rows)}개 업데이트"
                    )

            except Exception as e:
                logger.warning(f"지점 {branch_id} 키워드 업데이트 실패: {e}")
                continue

        logger.info(f"총 {updated_branches}개 지점 키워드 업데이트 완료")
        return updated_branches
