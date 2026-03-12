"""차량 모델 Repository

monthly_car_model_tag_stats + car_models_master + branch_car_models 기반 조회.
구 car_model_tags 테이블을 대체합니다.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

    async def _fetch_joined_stats(
        self,
        branch_id: int,
        car_model_name: str | None = None,
        period_from: str | None = None,
        period_to: str | None = None,
    ) -> list:
        """branch_car_models → car_models_master → monthly_car_model_tag_stats → tags → categories
        를 단일 JOIN 쿼리로 조회.

        Returns:
            Row 목록. 각 Row: car_model_id, model_name, tag_id, tag_name,
            category_name, period, positive_count, negative_count, neutral_count
        """
        stmt = (
            select(
                CarModelsMasterORM.id.label("car_model_id"),
                CarModelsMasterORM.model_name,
                MonthlyCarModelTagStatsORM.tag_id,
                MonthlyCarModelTagStatsORM.period,
                MonthlyCarModelTagStatsORM.positive_count,
                MonthlyCarModelTagStatsORM.negative_count,
                MonthlyCarModelTagStatsORM.neutral_count,
                TagORM.name.label("tag_name"),
                CategoryORM.name.label("category_name"),
            )
            .join(
                BranchCarModelORM,
                BranchCarModelORM.car_model_id == CarModelsMasterORM.id,
            )
            .join(
                MonthlyCarModelTagStatsORM,
                MonthlyCarModelTagStatsORM.car_model_id == CarModelsMasterORM.id,
            )
            .join(TagORM, TagORM.id == MonthlyCarModelTagStatsORM.tag_id)
            .outerjoin(CategoryORM, CategoryORM.id == TagORM.category_id)
            .where(BranchCarModelORM.branch_id == branch_id)
        )

        if car_model_name:
            stmt = stmt.where(CarModelsMasterORM.model_name == car_model_name)
        if period_from:
            stmt = stmt.where(MonthlyCarModelTagStatsORM.period >= period_from)
        if period_to:
            stmt = stmt.where(MonthlyCarModelTagStatsORM.period <= period_to)

        result = await self._session.execute(stmt)
        return result.all()

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
        rows = await self._fetch_joined_stats(branch_id, car_model_name=car_model)
        if not rows:
            return []

        # (car_model_id, tag_id)별 집계 (전 기간 합산)
        agg: dict[tuple[int, int], dict] = {}
        id_to_name: dict[int, str] = {}
        tag_id_to_name: dict[int, str] = {}

        for row in rows:
            cm_id = row.car_model_id
            tag_id = row.tag_id
            id_to_name[cm_id] = row.model_name or ""
            tag_id_to_name[tag_id] = row.tag_name or "기타"

            key = (cm_id, tag_id)
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

    async def get_vehicle_tags_raw(
        self,
        branch_id: int,
        period_from: str | None = None,
        period_to: str | None = None,
    ) -> dict:
        """차량별 태그 raw 데이터 (카테고리 포함, VehicleRankItem용)

        Args:
            period_from: 시작 기간 (YYYY-MM). None이면 전 기간.
            period_to: 종료 기간 (YYYY-MM). None이면 전 기간.

        Returns:
            {car_model: {"total_positive": N, "total_negative": N, "total_count": N,
             "tags": {tag_name: {"positive": N, "negative": N, "total": N, "category_name": str}}}}
        """
        rows = await self._fetch_joined_stats(
            branch_id, period_from=period_from, period_to=period_to
        )
        if not rows:
            return {}

        from domain.analysis.patterns import resolve_tag_category

        # (car_model_id, tag_id)별 집계
        agg: dict[tuple[int, int], dict] = {}
        meta: dict[tuple[int, int], tuple[str, str, str]] = {}  # → (model_name, tag_name, cat_name)

        for row in rows:
            cm_id = row.car_model_id
            tag_id = row.tag_id
            key = (cm_id, tag_id)

            if key not in agg:
                agg[key] = {"positive": 0, "negative": 0, "neutral": 0}
                cat_name = resolve_tag_category(row.tag_name or "", row.category_name or "")
                meta[key] = (row.model_name or "기타", row.tag_name or "기타", cat_name)

            agg[key]["positive"] += row.positive_count or 0
            agg[key]["negative"] += row.negative_count or 0
            agg[key]["neutral"] += row.neutral_count or 0

        car_data: dict[str, dict] = {}
        for (cm_id, tag_id), counts in agg.items():
            car_model_name, tag_name, cat_name = meta[(cm_id, tag_id)]
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
        rows = await self._fetch_joined_stats(branch_id)
        if not rows:
            return {}

        # (car_model_id, tag_id)별 집계
        agg: dict[tuple[int, int], dict] = {}
        meta: dict[tuple[int, int], tuple[str, str]] = {}  # → (model_name, tag_name)

        for row in rows:
            cm_id = row.car_model_id
            tag_id = row.tag_id
            key = (cm_id, tag_id)

            if key not in agg:
                agg[key] = {"positive": 0, "negative": 0, "neutral": 0}
                meta[key] = (row.model_name or "기타", row.tag_name or "기타")

            agg[key]["positive"] += row.positive_count or 0
            agg[key]["negative"] += row.negative_count or 0
            agg[key]["neutral"] += row.neutral_count or 0

        car_data: dict[str, dict] = {}
        for (cm_id, tag_id), counts in agg.items():
            car_model_name, tag_name = meta[(cm_id, tag_id)]
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
