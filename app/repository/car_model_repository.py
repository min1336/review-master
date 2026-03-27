"""차량 모델 Repository

branch_reviews + review_tag_mappings 기반 지점별 차량 태그 통계 조회.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from .orm_models import (
    BranchReviewORM,
    CategoryORM,
    ReviewTagMappingORM,
    TagORM,
)

logger = logging.getLogger(__name__)


class CarModelRepository:
    """차량 모델 태그 통계 조회 (branch_reviews + review_tag_mappings 기반)"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _fetch_joined_stats(
        self,
        branch_id: int,
        car_model_name: str | None = None,
        period_from: str | None = None,
        period_to: str | None = None,
    ) -> list:
        """branch_reviews + review_tag_mappings를 JOIN하여
        지점별 차량 태그 감정 통계를 집계.

        Returns:
            Row 목록. 각 Row: car_model_id(=0), model_name, tag_id, tag_name,
            category_name, period, positive_count, negative_count, neutral_count
        """
        br = BranchReviewORM
        rtm = ReviewTagMappingORM
        period_expr = func.to_char(br.review_date, "YYYY-MM")

        stmt = (
            select(
                literal(0).label("car_model_id"),
                br.car_model.label("model_name"),
                rtm.tag_id,
                period_expr.label("period"),
                func.count().filter(rtm.sentiment == "positive").label("positive_count"),
                func.count().filter(rtm.sentiment == "negative").label("negative_count"),
                func.count().filter(rtm.sentiment == "neutral").label("neutral_count"),
                TagORM.name.label("tag_name"),
                CategoryORM.name.label("category_name"),
            )
            .join(rtm, rtm.review_id == br.id)
            .join(TagORM, TagORM.id == rtm.tag_id)
            .outerjoin(CategoryORM, CategoryORM.id == TagORM.category_id)
            .where(
                br.branch_id == branch_id,
                br.car_model.isnot(None),
                br.car_model != "",
            )
            .group_by(br.car_model, rtm.tag_id, TagORM.name, CategoryORM.name,
                       period_expr)
        )

        if car_model_name:
            stmt = stmt.where(br.car_model == car_model_name)
        if period_from:
            stmt = stmt.where(period_expr >= period_from)
        if period_to:
            stmt = stmt.where(period_expr <= period_to)

        result = await self._session.execute(stmt)
        return result.all()

    async def get_car_model_tags(
        self, branch_id: int, car_model: str | None = None,
    ) -> list[dict]:
        """지점별 차량 모델 태그 통계 조회 (전 기간 합산)

        Returns:
            [{car_model, tag_name, positive_count, negative_count,
              neutral_count, total_count}, ...]
        """
        rows = await self._fetch_joined_stats(branch_id, car_model_name=car_model)
        if not rows:
            return []

        # (model_name, tag_id)별 집계 (전 기간 합산)
        agg: dict[tuple[str, int], dict] = {}
        tag_id_to_name: dict[int, str] = {}

        for row in rows:
            model_name = row.model_name or ""
            tag_id = row.tag_id
            tag_id_to_name[tag_id] = row.tag_name or "기타"

            key = (model_name, tag_id)
            if key not in agg:
                agg[key] = {"positive": 0, "negative": 0, "neutral": 0}
            agg[key]["positive"] += row.positive_count or 0
            agg[key]["negative"] += row.negative_count or 0
            agg[key]["neutral"] += row.neutral_count or 0

        results = []
        for (model_name, tag_id), counts in agg.items():
            total = counts["positive"] + counts["negative"] + counts["neutral"]
            results.append({
                "car_model": model_name,
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

        # (model_name, tag_id)별 집계
        agg: dict[tuple[str, int], dict] = {}
        meta: dict[tuple[str, int], tuple[str, str]] = {}  # → (tag_name, cat_name)

        for row in rows:
            model_name = row.model_name or "기타"
            tag_id = row.tag_id
            key = (model_name, tag_id)

            if key not in agg:
                agg[key] = {"positive": 0, "negative": 0, "neutral": 0}
                cat_name = resolve_tag_category(row.tag_name or "", row.category_name or "")
                meta[key] = (row.tag_name or "기타", cat_name)

            agg[key]["positive"] += row.positive_count or 0
            agg[key]["negative"] += row.negative_count or 0
            agg[key]["neutral"] += row.neutral_count or 0

        car_data: dict[str, dict] = {}
        for (model_name, tag_id), counts in agg.items():
            tag_name, cat_name = meta[(model_name, tag_id)]
            total = counts["positive"] + counts["negative"] + counts["neutral"]

            if model_name not in car_data:
                car_data[model_name] = {
                    "total_positive": 0,
                    "total_negative": 0,
                    "total_count": 0,
                    "tags": {},
                }
            car_data[model_name]["total_positive"] += counts["positive"]
            car_data[model_name]["total_negative"] += counts["negative"]
            car_data[model_name]["total_count"] += total
            car_data[model_name]["tags"][tag_name] = {
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

        # (model_name, tag_id)별 집계
        agg: dict[tuple[str, int], dict] = {}
        tag_id_to_name: dict[int, str] = {}

        for row in rows:
            model_name = row.model_name or "기타"
            tag_id = row.tag_id
            tag_id_to_name[tag_id] = row.tag_name or "기타"
            key = (model_name, tag_id)

            if key not in agg:
                agg[key] = {"positive": 0, "negative": 0, "neutral": 0}

            agg[key]["positive"] += row.positive_count or 0
            agg[key]["negative"] += row.negative_count or 0
            agg[key]["neutral"] += row.neutral_count or 0

        car_data: dict[str, dict] = {}
        for (model_name, tag_id), counts in agg.items():
            tag_name = tag_id_to_name.get(tag_id, "기타")
            total = counts["positive"] + counts["negative"] + counts["neutral"]

            if model_name not in car_data:
                car_data[model_name] = {
                    "total_count": 0,
                    "total_positive": 0,
                    "total_negative": 0,
                    "tags": {},
                }

            car_data[model_name]["total_count"] += total
            car_data[model_name]["total_positive"] += counts["positive"]
            car_data[model_name]["total_negative"] += counts["negative"]
            car_data[model_name]["tags"][tag_name] = {
                "positive": counts["positive"],
                "negative": counts["negative"],
                "neutral": counts["neutral"],
                "total": total,
            }

        return car_data
