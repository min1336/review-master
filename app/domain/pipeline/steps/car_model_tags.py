"""Step 5: 차량 마스터 + 지점-차량 관계 갱신

car_models_master, branch_car_models 테이블만 갱신합니다.
구 car_model_tags 테이블은 monthly_car_model_tag_stats (Step 9)로 대체되어 제거됨.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from schemas.dto import ProcessedReviewDTO

if TYPE_CHECKING:
    from supabase import AsyncClient

logger = logging.getLogger(__name__)


class CarModelTagAggregator:
    """차량 마스터 및 지점-차량 관계 갱신"""

    async def aggregate(
        self, client: AsyncClient, processed: list[ProcessedReviewDTO]
    ) -> dict:
        """car_models_master + branch_car_models upsert"""
        await self._upsert_car_models_master(client, processed)
        await self._upsert_branch_car_models(client, processed)

        car_models = {
            pr.review.car_model.strip()
            for pr in processed
            if pr.review.car_model.strip()
        }
        logger.info(f"차량 마스터/관계 갱신 완료: {len(car_models)}개 차량")
        return {"cars_processed": len(car_models)}

    async def _upsert_car_models_master(
        self, client: AsyncClient, processed: list[ProcessedReviewDTO]
    ) -> None:
        """리뷰에서 고유 car_model 이름 수집 → car_models_master upsert"""
        model_names: set[str] = set()
        for pr in processed:
            name = pr.review.car_model.strip()
            if name:
                model_names.add(name)

        if not model_names:
            return

        rows = [{"model_name": name} for name in model_names]
        try:
            batch_size = 500
            for i in range(0, len(rows), batch_size):
                batch = rows[i : i + batch_size]
                await (
                    client.table("car_models_master")
                    .upsert(batch, on_conflict="model_name")
                    .execute()
                )
            logger.info(f"car_models_master upsert 완료: {len(model_names)}개 모델")
        except Exception as e:
            logger.warning(f"car_models_master upsert 실패: {e}")

    async def _upsert_branch_car_models(
        self, client: AsyncClient, processed: list[ProcessedReviewDTO]
    ) -> None:
        """(branch_id, car_model) 쌍 → car_model_id 조회 → branch_car_models upsert"""
        pairs: set[tuple[int, str]] = set()
        for pr in processed:
            name = pr.review.car_model.strip()
            if name:
                pairs.add((pr.branch_id, name))

        if not pairs:
            return

        # car_models_master에서 name → id 조회
        model_names = list({p[1] for p in pairs})
        model_id_cache: dict[str, int] = {}
        try:
            result = await (
                client.table("car_models_master")
                .select("id, model_name")
                .in_("model_name", model_names)
                .execute()
            )
            for row in result.data:
                model_id_cache[row["model_name"]] = row["id"]
        except Exception as e:
            logger.warning(f"car_models_master 조회 실패: {e}")
            return

        rows: list[dict] = []
        for branch_id, model_name in pairs:
            car_model_id = model_id_cache.get(model_name)
            if car_model_id:
                rows.append({
                    "branch_id": branch_id,
                    "car_model_id": car_model_id,
                })

        if not rows:
            return

        try:
            batch_size = 500
            for i in range(0, len(rows), batch_size):
                batch = rows[i : i + batch_size]
                await (
                    client.table("branch_car_models")
                    .upsert(batch, on_conflict="branch_id,car_model_id")
                    .execute()
                )
            logger.info(f"branch_car_models upsert 완료: {len(rows)}건")
        except Exception as e:
            logger.warning(f"branch_car_models upsert 실패: {e}")
