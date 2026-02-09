"""Step 4: 태그 매핑 + branch_tags 갱신 (positive_count/negative_count 정확히 채움)"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from schemas.dto import ProcessedReviewDTO

if TYPE_CHECKING:
    from supabase import AsyncClient

logger = logging.getLogger(__name__)


class TagAggregator:
    """태그 매핑 + 지점별 태그 집계 (positive_count/negative_count)"""

    async def aggregate(
        self, client: AsyncClient, processed: list[ProcessedReviewDTO]
    ) -> dict:
        """tag_sentiments 기반으로 tags, keyword_mappings, branch_tags 갱신"""
        # 1. 지점별 태그+감정 메모리 집계
        branch_tag_data: dict[int, dict[str, dict]] = {}
        all_keywords_with_tags: dict[str, str] = {}

        for pr in processed:
            bid = pr.branch_id
            if bid not in branch_tag_data:
                branch_tag_data[bid] = {}

            for tag_name, sentiments in pr.tag_sentiments.items():
                if tag_name == "기타":
                    continue
                if tag_name not in branch_tag_data[bid]:
                    branch_tag_data[bid][tag_name] = {
                        "positive_count": 0,
                        "negative_count": 0,
                        "neutral_count": 0,
                    }

                counts = branch_tag_data[bid][tag_name]
                pos_keywords = sentiments.get("positive", [])
                neg_keywords = sentiments.get("negative", [])
                neu_keywords = sentiments.get("neutral", [])

                counts["positive_count"] += len(pos_keywords)
                counts["negative_count"] += len(neg_keywords)
                counts["neutral_count"] += len(neu_keywords)

                for kw in pos_keywords + neg_keywords + neu_keywords:
                    if kw not in all_keywords_with_tags:
                        all_keywords_with_tags[kw] = tag_name

        # 2. tags 배치 조회 → 없는 것만 개별 upsert
        tag_id_cache: dict[str, int] = {}
        all_tag_names: set[str] = set()
        for tag_data in branch_tag_data.values():
            all_tag_names.update(tag_data.keys())

        if all_tag_names:
            try:
                existing_tags = await (
                    client.table("tags")
                    .select("id, name")
                    .in_("name", list(all_tag_names))
                    .execute()
                )
                for row in existing_tags.data:
                    tag_id_cache[row["name"]] = row["id"]
            except Exception as e:
                logger.warning(f"tags 배치 조회 실패: {e}")

            # 캐시에 없는 태그만 개별 upsert
            missing_tags = all_tag_names - set(tag_id_cache.keys())
            for tag_name in missing_tags:
                try:
                    result = await (
                        client.table("tags")
                        .upsert(
                            {"name": tag_name, "is_active": True},
                            on_conflict="name",
                        )
                        .execute()
                    )
                    if result.data:
                        tag_id_cache[tag_name] = result.data[0]["id"]
                except Exception as e:
                    logger.warning(f"태그 upsert 실패 (tag={tag_name}): {e}")
                    continue

        # 3. keyword_mappings 배치 upsert
        keyword_rows: list[dict] = []
        for keyword, tag_name in all_keywords_with_tags.items():
            tag_id = tag_id_cache.get(tag_name)
            if tag_id:
                keyword_rows.append(
                    {"keyword": keyword, "tag_id": tag_id, "is_auto": True}
                )

        if keyword_rows:
            try:
                await (
                    client.table("keyword_mappings")
                    .upsert(keyword_rows, on_conflict="keyword")
                    .execute()
                )
            except Exception as e:
                logger.warning(f"keyword_mappings 배치 upsert 실패: {e}")

        # 4. branch_tags UPSERT (지점별 배치 조회 → 메모리 증분 → 배치 upsert)
        for branch_id, tag_data in branch_tag_data.items():
            tag_ids_for_branch: list[int] = [
                tag_id_cache[tn] for tn in tag_data if tn in tag_id_cache
            ]
            if not tag_ids_for_branch:
                continue

            try:
                # 지점의 기존 branch_tags를 한 번에 조회
                existing_result = await (
                    client.table("branch_tags")
                    .select("tag_id, positive_count, negative_count, count")
                    .eq("branch_id", branch_id)
                    .eq("period_type", "all")
                    .in_("tag_id", tag_ids_for_branch)
                    .execute()
                )

                existing_map: dict[int, dict] = {}
                for row in existing_result.data:
                    existing_map[row["tag_id"]] = row

                # 메모리에서 증분 계산 후 배치 upsert
                upsert_rows: list[dict] = []
                for tag_name, counts in tag_data.items():
                    tag_id = tag_id_cache.get(tag_name)
                    if not tag_id:
                        continue

                    existing = existing_map.get(tag_id)
                    if existing:
                        old_pos = existing.get("positive_count", 0) or 0
                        old_neg = existing.get("negative_count", 0) or 0
                        old_count = existing.get("count", 0) or 0
                        new_pos = old_pos + counts["positive_count"]
                        new_neg = old_neg + counts["negative_count"]
                    else:
                        new_pos = counts["positive_count"]
                        new_neg = counts["negative_count"]
                        old_count = 0

                    new_total = (
                        old_count
                        + counts["positive_count"]
                        + counts["negative_count"]
                        + counts["neutral_count"]
                    )

                    upsert_rows.append({
                        "branch_id": branch_id,
                        "tag_id": tag_id,
                        "period_type": "all",
                        "positive_count": new_pos,
                        "negative_count": new_neg,
                        "count": new_total,
                        "weighted_score": float(new_total),
                    })

                if upsert_rows:
                    await (
                        client.table("branch_tags")
                        .upsert(
                            upsert_rows,
                            on_conflict="branch_id,tag_id,period_type",
                        )
                        .execute()
                    )

            except Exception as e:
                logger.warning(
                    f"branch_tags 업데이트 실패 (branch_id={branch_id}): {e}"
                )
                continue

        return {"branches": len(branch_tag_data), "tags": len(tag_id_cache)}
