"""Step 5: 차량별 태그 집계 (car_model_tags 테이블 갱신)"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from schemas.dto import ProcessedReviewDTO

if TYPE_CHECKING:
    from supabase import AsyncClient

logger = logging.getLogger(__name__)


class CarModelTagAggregator:
    """차량별 태그 감정 집계 (positive_count/negative_count/neutral_count)"""

    async def aggregate(
        self, client: AsyncClient, processed: list[ProcessedReviewDTO]
    ) -> dict:
        """tag_sentiments 기반으로 차량+태그별 감정 통계 집계 및 DB 저장"""
        # 1. 지점+차량+태그별 감정 메모리 집계
        car_tag_data: dict[tuple[int, str, str], dict[str, int]] = {}

        for pr in processed:
            bid = pr.branch_id
            car_model = pr.review.car_model.strip()

            # 차량 정보가 없는 리뷰는 건너뜀
            if not car_model:
                continue

            for tag_name, sentiments in pr.tag_sentiments.items():
                if tag_name == "기타":
                    continue

                key = (bid, car_model, tag_name)
                if key not in car_tag_data:
                    car_tag_data[key] = {
                        "positive_count": 0,
                        "negative_count": 0,
                        "neutral_count": 0,
                    }

                counts = car_tag_data[key]
                pos_keywords = sentiments.get("positive", [])
                neg_keywords = sentiments.get("negative", [])
                neu_keywords = sentiments.get("neutral", [])

                counts["positive_count"] += len(pos_keywords)
                counts["negative_count"] += len(neg_keywords)
                counts["neutral_count"] += len(neu_keywords)

        if not car_tag_data:
            logger.info("차량 정보가 있는 리뷰가 없어 car_model_tags 업데이트를 건너뜁니다.")
            return {"cars_processed": 0, "tags_saved": 0}

        # 2. tags 배치 조회로 tag_id 캐시
        tag_id_cache: dict[str, int] = {}
        all_tag_names: set[str] = {key[2] for key in car_tag_data.keys()}

        if all_tag_names:
            try:
                result = await (
                    client.table("tags")
                    .select("id, name")
                    .in_("name", list(all_tag_names))
                    .execute()
                )
                for row in result.data:
                    tag_id_cache[row["name"]] = row["id"]
            except Exception as e:
                logger.warning(f"tags 배치 조회 실패: {e}")

            missing_tags = all_tag_names - set(tag_id_cache.keys())
            for tag_name in missing_tags:
                logger.warning(f"태그 ID를 찾을 수 없음 (tag={tag_name})")

        # 3. 지점별로 기존 car_model_tags 배치 조회 → 메모리 증분 → 배치 upsert
        # 먼저 지점별로 그룹화
        branch_groups: dict[int, list[tuple[tuple[int, str, str], dict[str, int]]]] = {}
        for key, counts in car_tag_data.items():
            branch_id = key[0]
            if branch_id not in branch_groups:
                branch_groups[branch_id] = []
            branch_groups[branch_id].append((key, counts))

        cars_processed: set[str] = set()
        tags_saved = 0

        for branch_id, items in branch_groups.items():
            # 이 지점에 해당하는 tag_id 목록
            tag_ids_for_branch: list[int] = []
            for (_, _, tag_name), _ in items:
                tid = tag_id_cache.get(tag_name)
                if tid and tid not in tag_ids_for_branch:
                    tag_ids_for_branch.append(tid)

            if not tag_ids_for_branch:
                continue

            try:
                # 지점의 기존 car_model_tags를 한 번에 조회
                existing_result = await (
                    client.table("car_model_tags")
                    .select("car_model, tag_id, positive_count, negative_count, neutral_count, total_count")
                    .eq("branch_id", branch_id)
                    .eq("period_type", "all")
                    .in_("tag_id", tag_ids_for_branch)
                    .execute()
                )

                # (car_model, tag_id) → row 매핑
                existing_map: dict[tuple[str, int], dict] = {}
                for row in existing_result.data:
                    existing_map[(row["car_model"], row["tag_id"])] = row

                # 메모리 증분 계산 → 배치 upsert 행 생성
                upsert_rows: list[dict] = []
                for (_, car_model, tag_name), counts in items:
                    tag_id = tag_id_cache.get(tag_name)
                    if not tag_id:
                        continue

                    existing = existing_map.get((car_model, tag_id))
                    if existing:
                        new_pos = (existing.get("positive_count", 0) or 0) + counts["positive_count"]
                        new_neg = (existing.get("negative_count", 0) or 0) + counts["negative_count"]
                        new_neu = (existing.get("neutral_count", 0) or 0) + counts["neutral_count"]
                    else:
                        new_pos = counts["positive_count"]
                        new_neg = counts["negative_count"]
                        new_neu = counts["neutral_count"]

                    new_total = new_pos + new_neg + new_neu

                    upsert_rows.append({
                        "branch_id": branch_id,
                        "car_model": car_model,
                        "tag_id": tag_id,
                        "period_type": "all",
                        "positive_count": new_pos,
                        "negative_count": new_neg,
                        "neutral_count": new_neu,
                        "total_count": new_total,
                    })

                    cars_processed.add(car_model)
                    tags_saved += 1

                if upsert_rows:
                    await (
                        client.table("car_model_tags")
                        .upsert(
                            upsert_rows,
                            on_conflict="branch_id,car_model,tag_id,period_type",
                        )
                        .execute()
                    )

            except Exception as e:
                logger.warning(
                    f"car_model_tags 업데이트 실패 (branch_id={branch_id}): {e}"
                )
                continue

        logger.info(
            f"차량별 태그 집계 완료: {len(cars_processed)}개 차량, {tags_saved}개 태그 저장"
        )
        return {"cars_processed": len(cars_processed), "tags_saved": tags_saved}
