"""Step 4: 태그 매핑 + branch_tags 갱신 (positive_count/negative_count 정확히 채움)"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.decay import compute_decay
from core.timezone import utc_now
from repository.orm_models import BranchTagORM, CategoryORM, KeywordMappingORM, TagORM
from schemas.dto import ProcessedReviewDTO

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class TagAggregator:
    """태그 매핑 + 지점별 태그 집계 (positive_count/negative_count)"""

    async def aggregate(
        self, session: AsyncSession, processed: list[ProcessedReviewDTO]
    ) -> dict:
        """tag_sentiments 기반으로 tags, keyword_mappings, branch_tags 갱신"""
        # 1. 지점별 태그+감정 메모리 집계
        branch_tag_data: dict[int, dict[str, dict]] = {}
        all_keywords_with_tags: dict[str, str] = {}
        today = utc_now()

        for pr in processed:
            bid = pr.branch_id
            if bid not in branch_tag_data:
                branch_tag_data[bid] = {}

            decay = compute_decay(pr.review.created_at, today)

            for tag_name, sentiments in pr.tag_sentiments.items():
                if tag_name == "기타":
                    continue
                if tag_name not in branch_tag_data[bid]:
                    branch_tag_data[bid][tag_name] = {
                        "positive_count": 0,
                        "negative_count": 0,
                        "neutral_count": 0,
                        "weighted_delta": 0.0,
                    }

                counts = branch_tag_data[bid][tag_name]
                pos_keywords = sentiments.get("positive", [])
                neg_keywords = sentiments.get("negative", [])
                neu_keywords = sentiments.get("neutral", [])

                counts["positive_count"] += len(pos_keywords)
                counts["negative_count"] += len(neg_keywords)
                counts["neutral_count"] += len(neu_keywords)
                counts["weighted_delta"] += (
                    len(pos_keywords) + len(neg_keywords) + len(neu_keywords)
                ) * decay

                for kw in pos_keywords + neg_keywords + neu_keywords:
                    if kw not in all_keywords_with_tags:
                        all_keywords_with_tags[kw] = tag_name

        # 2. tags 배치 조회 -> 없는 것만 개별 upsert
        tag_id_cache: dict[str, int] = {}
        all_tag_names: set[str] = set()
        for tag_data in branch_tag_data.values():
            all_tag_names.update(tag_data.keys())

        if all_tag_names:
            try:
                result = await session.execute(
                    select(TagORM.id, TagORM.name)
                    .where(TagORM.name.in_(list(all_tag_names)))
                )
                for row in result.all():
                    tag_id_cache[row.name] = row.id
            except Exception as e:
                logger.warning(f"tags 배치 조회 실패: {e}")

            # 캐시에 없는 태그만 개별 upsert
            missing_tags = all_tag_names - set(tag_id_cache.keys())

            # tag_name → (category_name, group) 매핑 빌드 (circular import 방지: 함수 내 import)
            from domain.analysis.patterns import TAG_REGISTRY

            tag_to_category_name: dict[str, str] = {}
            tag_to_group: dict[str, str] = {}
            for cat_name, cat_meta in TAG_REGISTRY.items():
                # 카테고리 이름 자체도 태그로 쓰일 수 있음 (ABSA 경로)
                tag_to_category_name[cat_name] = cat_name
                tag_to_group[cat_name] = cat_meta.group
                # 세분화 서브태그
                for sub_tag_name in cat_meta.tags:
                    tag_to_category_name[sub_tag_name] = cat_name
                    tag_to_group[sub_tag_name] = cat_meta.group

            # categories 테이블에서 category_name → category_id 조회
            category_name_to_id: dict[str, int] = {}
            needed_cat_names = {
                tag_to_category_name[t]
                for t in missing_tags
                if t in tag_to_category_name
            }
            if needed_cat_names:
                try:
                    cat_result = await session.execute(
                        select(CategoryORM.id, CategoryORM.name).where(
                            CategoryORM.name.in_(list(needed_cat_names))
                        )
                    )
                    for cat_row in cat_result.all():
                        category_name_to_id[cat_row.name] = cat_row.id
                except Exception as e:
                    logger.warning(f"categories 조회 실패: {e}")

            GROUP_TO_TAG_TYPE = {"affiliate": "company", "vehicle": "vehicle"}

            for tag_name in missing_tags:
                try:
                    cat_name = tag_to_category_name.get(tag_name)
                    cat_id = category_name_to_id.get(cat_name) if cat_name else None
                    group = tag_to_group.get(tag_name)
                    tag_type = GROUP_TO_TAG_TYPE.get(group)

                    insert_values: dict = {"name": tag_name, "is_active": True}
                    update_set: dict = {"is_active": True}
                    if cat_id is not None:
                        insert_values["category_id"] = cat_id
                        # on_conflict: category_id가 NULL이면 덮어쓰기
                        update_set["category_id"] = cat_id
                    if tag_type is not None:
                        insert_values["tag_type"] = tag_type
                        update_set["tag_type"] = tag_type

                    stmt = (
                        pg_insert(TagORM.__table__)
                        .values(**insert_values)
                        .on_conflict_do_update(
                            index_elements=["name"],
                            set_=update_set,
                        )
                        .returning(TagORM.__table__.c.id)
                    )
                    result = await session.execute(stmt)
                    row = result.scalar_one_or_none()
                    if row is not None:
                        tag_id_cache[tag_name] = row
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
                for row_data in keyword_rows:
                    stmt = (
                        pg_insert(KeywordMappingORM.__table__)
                        .values(**row_data)
                        .on_conflict_do_update(
                            index_elements=["keyword"],
                            set_={
                                "tag_id": row_data["tag_id"],
                                "is_auto": row_data["is_auto"],
                            },
                        )
                    )
                    await session.execute(stmt)
            except Exception as e:
                logger.warning(f"keyword_mappings 배치 upsert 실패: {e}")

        # 4. branch_tags UPSERT (지점별 배치 조회 -> 메모리 증분 -> 배치 upsert)
        for branch_id, tag_data in branch_tag_data.items():
            tag_ids_for_branch: list[int] = [
                tag_id_cache[tn] for tn in tag_data if tn in tag_id_cache
            ]
            if not tag_ids_for_branch:
                continue

            try:
                # 지점의 기존 branch_tags를 한 번에 조회 (weighted_score 포함)
                existing_result = await session.execute(
                    select(
                        BranchTagORM.tag_id,
                        BranchTagORM.positive_count,
                        BranchTagORM.negative_count,
                        BranchTagORM.neutral_count,
                        BranchTagORM.count,
                        BranchTagORM.weighted_score,
                    )
                    .where(BranchTagORM.branch_id == branch_id)
                    .where(BranchTagORM.period_type == "all")
                    .where(BranchTagORM.tag_id.in_(tag_ids_for_branch))
                )

                existing_map: dict[int, dict] = {}
                for row in existing_result.all():
                    existing_map[row.tag_id] = {
                        "positive_count": row.positive_count,
                        "negative_count": row.negative_count,
                        "neutral_count": row.neutral_count,
                        "count": row.count,
                        "weighted_score": row.weighted_score,
                    }

                # 메모리에서 증분 계산 후 배치 upsert
                for tag_name, counts in tag_data.items():
                    tag_id = tag_id_cache.get(tag_name)
                    if not tag_id:
                        continue

                    existing = existing_map.get(tag_id)
                    if existing:
                        old_pos = existing.get("positive_count", 0) or 0
                        old_neg = existing.get("negative_count", 0) or 0
                        old_neu = existing.get("neutral_count", 0) or 0
                        old_count = existing.get("count", 0) or 0
                        new_pos = old_pos + counts["positive_count"]
                        new_neg = old_neg + counts["negative_count"]
                        new_neu = old_neu + counts["neutral_count"]
                    else:
                        new_pos = counts["positive_count"]
                        new_neg = counts["negative_count"]
                        new_neu = counts["neutral_count"]
                        old_count = 0

                    new_total = (
                        old_count
                        + counts["positive_count"]
                        + counts["negative_count"]
                        + counts["neutral_count"]
                    )

                    existing_weighted = (existing.get("weighted_score") or 0.0) if existing else 0.0
                    incremental = (
                        counts["positive_count"]
                        + counts["negative_count"]
                        + counts["neutral_count"]
                    )
                    weighted_delta = counts.get("weighted_delta") or float(incremental)

                    values = {
                        "branch_id": branch_id,
                        "tag_id": tag_id,
                        "period_type": "all",
                        "positive_count": new_pos,
                        "negative_count": new_neg,
                        "neutral_count": new_neu,
                        "count": new_total,
                        "weighted_score": existing_weighted + weighted_delta,
                    }
                    stmt = (
                        pg_insert(BranchTagORM.__table__)
                        .values(**values)
                        .on_conflict_do_update(
                            index_elements=["branch_id", "tag_id", "period_type"],
                            set_={
                                "positive_count": values["positive_count"],
                                "negative_count": values["negative_count"],
                                "neutral_count": values["neutral_count"],
                                "count": values["count"],
                                "weighted_score": values["weighted_score"],
                            },
                        )
                    )
                    await session.execute(stmt)

            except Exception as e:
                logger.warning(
                    f"branch_tags 업데이트 실패 (branch_id={branch_id}): {e}"
                )
                continue

        return {"branches": len(branch_tag_data), "tags": len(tag_id_cache)}
