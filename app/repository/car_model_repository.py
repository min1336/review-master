"""차량 모델 Repository

monthly_car_model_tag_stats + car_models_master + branch_car_models 기반 조회.
구 car_model_tags 테이블을 대체합니다.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .orm_models import (
    BranchCarModelORM,
    CarModelsMasterORM,
    CategoryORM,
    MonthlyCarModelTagStatsORM,
    TagORM,
)

logger = logging.getLogger(__name__)


class CarModelRepository:
    """차량 모델 태그 통계 조회 (monthly_car_model_tag_stats 기반)"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _get_branch_car_model_ids(
        self, branch_id: int, car_model_name: str | None = None,
    ) -> tuple[dict[int, str], dict[str, int]]:
        """branch_car_models + car_models_master에서 지점 차량 조회

        Returns:
            (id_to_name, name_to_id) 매핑 튜플
        """
        stmt = (
            select(BranchCarModelORM)
            .options(selectinload(BranchCarModelORM.car_model))
            .where(BranchCarModelORM.branch_id == branch_id)
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()

        id_to_name: dict[int, str] = {}
        name_to_id: dict[str, int] = {}
        for row in rows:
            master = row.car_model
            if not master:
                continue
            mid = master.id
            name = master.model_name or ""
            if mid and name:
                if car_model_name and name != car_model_name:
                    continue
                id_to_name[mid] = name
                name_to_id[name] = mid

        return id_to_name, name_to_id

    async def _fetch_tag_stats_rows(
        self, car_model_ids: list[int], batch_size: int = 100,
    ) -> list[MonthlyCarModelTagStatsORM]:
        """monthly_car_model_tag_stats에서 태그 통계 행 일괄 조회"""
        all_rows: list[MonthlyCarModelTagStatsORM] = []
        for i in range(0, len(car_model_ids), batch_size):
            batch_ids = car_model_ids[i : i + batch_size]
            result = await self._session.execute(
                select(MonthlyCarModelTagStatsORM).where(
                    MonthlyCarModelTagStatsORM.car_model_id.in_(batch_ids)
                )
            )
            all_rows.extend(result.scalars().all())
        return all_rows

    async def get_car_model_tags(
        self, branch_id: int, car_model: str | None = None,
    ) -> list[dict]:
        """지점별 차량 모델 태그 통계 조회

        monthly_car_model_tag_stats에서 전 기간 집계.
        car_model_tags 테이블의 get 로직을 대체합니다.

        Returns:
            [{car_model, tag_name, positive_count, negative_count,
              neutral_count, total_count}, ...]
        """
        id_to_name, _ = await self._get_branch_car_model_ids(branch_id, car_model)
        if not id_to_name:
            return []

        car_model_ids = list(id_to_name.keys())
        all_rows = await self._fetch_tag_stats_rows(car_model_ids)
        if not all_rows:
            return []

        # tag_id → name 매핑
        tag_ids = list({row.tag_id for row in all_rows})
        tag_id_to_name = await self._get_tag_names(tag_ids)

        # (car_model_id, tag_id)별 집계 (전 기간 합산)
        agg: dict[tuple[int, int], dict] = {}
        for row in all_rows:
            key = (row.car_model_id, row.tag_id)
            if key not in agg:
                agg[key] = {"positive": 0, "negative": 0, "neutral": 0}
            agg[key]["positive"] += row.positive_count or 0
            agg[key]["negative"] += row.negative_count or 0
            agg[key]["neutral"] += row.neutral_count or 0

        results = []
        for (cm_id, tag_id), counts in agg.items():
            total = counts["positive"] + counts["negative"] + counts["neutral"]
            results.append({
                "car_model": id_to_name.get(cm_id, ""),
                "tag_name": tag_id_to_name.get(tag_id, "기타"),
                "tag_id": tag_id,
                "positive_count": counts["positive"],
                "negative_count": counts["negative"],
                "neutral_count": counts["neutral"],
                "total_count": total,
            })

        return results

    async def get_vehicle_tags_raw(self, branch_id: int) -> dict:
        """차량별 태그 raw 데이터 (카테고리 포함, VehicleRankItem용)

        Returns:
            {car_model: {"total_positive": N, "total_negative": N, "total_count": N,
             "tags": {tag_name: {"positive": N, "negative": N, "total": N, "category_name": str}}}}
        """
        id_to_name, _ = await self._get_branch_car_model_ids(branch_id)
        if not id_to_name:
            return {}

        car_model_ids = list(id_to_name.keys())
        all_rows = await self._fetch_tag_stats_rows(car_model_ids)
        if not all_rows:
            return {}

        # tag_id → (name, category_name) 매핑
        tag_ids = list({row.tag_id for row in all_rows})
        tag_info_map = await self._get_tag_info_with_category(tag_ids)

        # (car_model_id, tag_id)별 집계
        agg: dict[tuple[int, int], dict] = {}
        for row in all_rows:
            key = (row.car_model_id, row.tag_id)
            if key not in agg:
                agg[key] = {"positive": 0, "negative": 0, "neutral": 0}
            agg[key]["positive"] += row.positive_count or 0
            agg[key]["negative"] += row.negative_count or 0
            agg[key]["neutral"] += row.neutral_count or 0

        car_data: dict[str, dict] = {}
        for (cm_id, tag_id), counts in agg.items():
            car_model_name = id_to_name.get(cm_id, "기타")
            tag_name, cat_name = tag_info_map.get(tag_id, ("기타", ""))
            total = counts["positive"] + counts["negative"] + counts["neutral"]

            if car_model_name not in car_data:
                car_data[car_model_name] = {
                    "total_positive": 0,
                    "total_negative": 0,
                    "total_count": 0,
                    "tags": {},
                }
            car_data[car_model_name]["total_positive"] += counts["positive"]
            car_data[car_model_name]["total_negative"] += counts["negative"]
            car_data[car_model_name]["total_count"] += total
            car_data[car_model_name]["tags"][tag_name] = {
                "positive": counts["positive"],
                "negative": counts["negative"],
                "total": total,
                "category_name": cat_name,
            }

        return car_data

    async def get_vehicle_analysis_data(self, branch_id: int) -> dict:
        """차량 분석용 데이터 조회 (VehicleAnalysis 변환 전 raw 데이터)

        Returns:
            {car_model: {"total_count": N, "total_positive": N, "total_negative": N,
             "tags": {tag_name: {"positive": N, "negative": N, "neutral": N, "total": N}}}}
        """
        id_to_name, _ = await self._get_branch_car_model_ids(branch_id)
        if not id_to_name:
            return {}

        car_model_ids = list(id_to_name.keys())
        all_rows = await self._fetch_tag_stats_rows(car_model_ids)
        if not all_rows:
            return {}

        tag_ids = list({row.tag_id for row in all_rows})
        tag_id_to_name = await self._get_tag_names(tag_ids)

        # (car_model_id, tag_id)별 집계
        agg: dict[tuple[int, int], dict] = {}
        for row in all_rows:
            key = (row.car_model_id, row.tag_id)
            if key not in agg:
                agg[key] = {"positive": 0, "negative": 0, "neutral": 0}
            agg[key]["positive"] += row.positive_count or 0
            agg[key]["negative"] += row.negative_count or 0
            agg[key]["neutral"] += row.neutral_count or 0

        car_data: dict[str, dict] = {}
        for (cm_id, tag_id), counts in agg.items():
            car_model_name = id_to_name.get(cm_id, "기타")
            tag_name = tag_id_to_name.get(tag_id, "기타")
            total = counts["positive"] + counts["negative"] + counts["neutral"]

            if car_model_name not in car_data:
                car_data[car_model_name] = {
                    "total_count": 0,
                    "total_positive": 0,
                    "total_negative": 0,
                    "tags": {},
                }

            car_data[car_model_name]["total_count"] += total
            car_data[car_model_name]["total_positive"] += counts["positive"]
            car_data[car_model_name]["total_negative"] += counts["negative"]
            car_data[car_model_name]["tags"][tag_name] = {
                "positive": counts["positive"],
                "negative": counts["negative"],
                "neutral": counts["neutral"],
                "total": total,
            }

        return car_data

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    async def _get_tag_names(self, tag_ids: list[int]) -> dict[int, str]:
        """tag_id → name 매핑"""
        if not tag_ids:
            return {}
        result = await self._session.execute(
            select(TagORM.id, TagORM.name).where(TagORM.id.in_(tag_ids))
        )
        return {row.id: row.name for row in result.all()}

    async def _get_tag_info_with_category(
        self, tag_ids: list[int],
    ) -> dict[int, tuple[str, str]]:
        """tag_id → (tag_name, category_name) 매핑"""
        if not tag_ids:
            return {}
        result = await self._session.execute(
            select(TagORM)
            .options(selectinload(TagORM.category))
            .where(TagORM.id.in_(tag_ids))
        )
        rows = result.scalars().all()

        mapping: dict[int, tuple[str, str]] = {}
        for row in rows:
            cat_name = row.category.name if row.category else ""
            mapping[row.id] = (row.name, cat_name)
        return mapping
