"""Step 9: monthly_car_model_tag_stats 저장 (차량×월×태그별 감정 통계)"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from schemas.dto import ProcessedReviewDTO

if TYPE_CHECKING:
    from supabase import AsyncClient

logger = logging.getLogger(__name__)


class MonthlyCarModelStatsUpdater:
    """monthly_car_model_tag_stats 테이블 적재"""

    async def update(
        self, client: AsyncClient, processed: list[ProcessedReviewDTO]
    ) -> int:
        """(car_model, period, tag_name) 메모리 집계 → car_model_id/tag_id 변환 → upsert"""
        # 1. 메모리 집계
        groups: dict[tuple[str, str, str], dict[str, int]] = {}

        for pr in processed:
            car_model = pr.review.car_model.strip()
            if not car_model:
                continue
            period = self._get_period(pr)
            if not period:
                continue

            for tag_name, sentiments in pr.tag_sentiments.items():
                if tag_name == "기타":
                    continue
                key = (car_model, period, tag_name)
                if key not in groups:
                    groups[key] = {"positive": 0, "negative": 0, "neutral": 0}
                g = groups[key]
                g["positive"] += len(sentiments.get("positive", []))
                g["negative"] += len(sentiments.get("negative", []))
                g["neutral"] += len(sentiments.get("neutral", []))

        if not groups:
            return 0

        # 2. car_models_master에서 car_model_id 일괄 조회
        all_model_names = list({k[0] for k in groups})
        model_id_cache: dict[str, int] = {}
        try:
            result = await (
                client.table("car_models_master")
                .select("id, model_name")
                .in_("model_name", all_model_names)
                .execute()
            )
            for row in result.data:
                model_id_cache[row["model_name"]] = row["id"]
        except Exception as e:
            logger.warning(f"car_models_master 조회 실패: {e}")
            return 0

        # 3. tags에서 tag_id 일괄 조회
        all_tag_names = list({k[2] for k in groups})
        tag_id_cache: dict[str, int] = {}
        try:
            result = await (
                client.table("tags")
                .select("id, name")
                .in_("name", all_tag_names)
                .execute()
            )
            for row in result.data:
                tag_id_cache[row["name"]] = row["id"]
        except Exception as e:
            logger.warning(f"tags 조회 실패: {e}")
            return 0

        # 4. 기존 데이터 SELECT → 증분 합산 → UPSERT
        saved = 0
        for (car_model, period, tag_name), counts in groups.items():
            car_model_id = model_id_cache.get(car_model)
            tag_id = tag_id_cache.get(tag_name)
            if not car_model_id or not tag_id:
                continue

            try:
                existing = await (
                    client.table("monthly_car_model_tag_stats")
                    .select("*")
                    .eq("car_model_id", car_model_id)
                    .eq("period", period)
                    .eq("tag_id", tag_id)
                    .execute()
                )
                old = existing.data[0] if existing.data else {}

                new_pos = (old.get("positive_count", 0) or 0) + counts["positive"]
                new_neg = (old.get("negative_count", 0) or 0) + counts["negative"]
                new_neu = (old.get("neutral_count", 0) or 0) + counts["neutral"]

                await (
                    client.table("monthly_car_model_tag_stats")
                    .upsert(
                        {
                            "car_model_id": car_model_id,
                            "period": period,
                            "tag_id": tag_id,
                            "positive_count": new_pos,
                            "negative_count": new_neg,
                            "neutral_count": new_neu,
                        },
                        on_conflict="car_model_id,period,tag_id",
                    )
                    .execute()
                )
                saved += 1
            except Exception as e:
                logger.warning(
                    f"monthly_car_model_tag_stats upsert 실패 "
                    f"(model={car_model}, period={period}, tag={tag_name}): {e}"
                )

        logger.info(f"monthly_car_model_tag_stats 저장 완료: {saved}건")
        return saved

    @staticmethod
    def _get_period(pr: ProcessedReviewDTO) -> str | None:
        """리뷰의 created_at에서 YYYY-MM 형식 period 추출"""
        if pr.review.created_at:
            return pr.review.created_at.strftime("%Y-%m")
        return None
