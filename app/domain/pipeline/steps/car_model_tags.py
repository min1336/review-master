"""Step 5: 차량 마스터 + 지점-차량 관계 갱신

car_models_master, branch_car_models 테이블만 갱신합니다.
구 car_model_tags 테이블은 monthly_car_model_tag_stats (Step 9)로 대체되어 제거됨.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from repository.orm_models import BranchCarModelORM, CarModelsMasterORM
from schemas.dto import ProcessedReviewDTO

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class CarModelTagAggregator:
    """차량 마스터 및 지점-차량 관계 갱신"""

    async def aggregate(
        self, session: AsyncSession, processed: list[ProcessedReviewDTO]
    ) -> dict:
        """car_models_master + branch_car_models upsert"""
        await self._upsert_car_models_master(session, processed)
        await self._upsert_branch_car_models(session, processed)

        car_models = {
            pr.review.car_model.strip()
            for pr in processed
            if pr.review.car_model.strip()
        }
        logger.info("차량 마스터/관계 갱신 완료: %s개 차량", len(car_models))
        return {"cars_processed": len(car_models)}

    async def _upsert_car_models_master(
        self, session: AsyncSession, processed: list[ProcessedReviewDTO]
    ) -> None:
        """리뷰에서 고유 car_model 이름 수집 -> car_models_master upsert"""
        model_names: set[str] = set()
        for pr in processed:
            name = pr.review.car_model.strip()
            if name:
                model_names.add(name)

        if not model_names:
            return

        try:
            for name in model_names:
                stmt = (
                    pg_insert(CarModelsMasterORM.__table__)
                    .values(model_name=name)
                    .on_conflict_do_update(
                        index_elements=["model_name"],
                        set_={"model_name": name},
                    )
                )
                await session.execute(stmt)
            logger.info("car_models_master upsert 완료: %s개 모델", len(model_names))
        except Exception as e:
            logger.warning("car_models_master upsert 실패: %s", e)

    async def _upsert_branch_car_models(
        self, session: AsyncSession, processed: list[ProcessedReviewDTO]
    ) -> None:
        """(branch_id, car_model) 쌍 -> car_model_id 조회 -> branch_car_models upsert"""
        pairs: set[tuple[int, str]] = set()
        for pr in processed:
            name = pr.review.car_model.strip()
            if name:
                pairs.add((pr.branch_id, name))

        if not pairs:
            return

        # car_models_master에서 name -> id 조회
        model_names = list({p[1] for p in pairs})
        model_id_cache: dict[str, int] = {}
        try:
            result = await session.execute(
                select(CarModelsMasterORM.id, CarModelsMasterORM.model_name)
                .where(CarModelsMasterORM.model_name.in_(model_names))
            )
            for row in result.all():
                model_id_cache[row.model_name] = row.id
        except Exception as e:
            logger.warning("car_models_master 조회 실패: %s", e)
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
            for row_data in rows:
                stmt = (
                    pg_insert(BranchCarModelORM.__table__)
                    .values(**row_data)
                    .on_conflict_do_update(
                        index_elements=["branch_id", "car_model_id"],
                        set_={"branch_id": row_data["branch_id"]},
                    )
                )
                await session.execute(stmt)
            logger.info("branch_car_models upsert 완료: %s건", len(rows))
        except Exception as e:
            logger.warning("branch_car_models upsert 실패: %s", e)
