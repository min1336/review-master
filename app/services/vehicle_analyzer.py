"""차량 분석 서비스

차량별 태그 데이터 조회 및 순위 산출을 담당합니다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from domain.analysis.patterns import VEHICLE_CATEGORIES

if TYPE_CHECKING:
    from services.report_service import VehicleAnalysis, VehicleRankItem

logger = logging.getLogger(__name__)


class VehicleAnalyzer:
    """차량별 평가 분석"""

    # ----------------------------------------------------------------
    # 공통 변환 헬퍼
    # ----------------------------------------------------------------

    def _convert_to_vehicle_analysis(self, car_data: dict) -> list:
        """car_data dict → VehicleAnalysis 리스트 변환 (공통 로직)

        car_data 구조:
            {car_model: {"total_count": N, "total_positive": N, "total_negative": N,
                         "tags": {tag_name: {"positive": N, "negative": N, ...}}}}
        """
        from services.report_service import VehicleAnalysis

        vehicle_list: list[VehicleAnalysis] = []

        for car_model, data in sorted(
            car_data.items(), key=lambda x: x[1]["total_count"], reverse=True
        ):
            total = data["total_count"]
            if total == 0:
                continue

            total_positive = data["total_positive"]
            total_negative = data["total_negative"]

            positive_ratio = total_positive / total
            negative_ratio = total_negative / total
            avg_sentiment = (positive_ratio - negative_ratio + 1) / 2

            top_praise_tag = ""
            max_positive = 0
            top_issue_tag = ""
            max_negative = 0

            for tag_name, tag_stats in data.get("tags", {}).items():
                if tag_stats["positive"] > max_positive:
                    max_positive = tag_stats["positive"]
                    top_praise_tag = f"{tag_name}({max_positive}건)"
                if tag_stats["negative"] > max_negative:
                    max_negative = tag_stats["negative"]
                    top_issue_tag = f"{tag_name}({max_negative}건)"

            like_ratio = int(round((total_positive / total) * 100))
            dislike_ratio = int(round((total_negative / total) * 100))

            vehicle_list.append(
                VehicleAnalysis(
                    model=car_model,
                    count=total,
                    avg_sentiment=round(avg_sentiment, 2),
                    top_praise=top_praise_tag,
                    top_issue=top_issue_tag,
                    like_ratio=like_ratio,
                    dislike_ratio=dislike_ratio,
                )
            )

        return vehicle_list

    # ----------------------------------------------------------------
    # 공개 메서드
    # ----------------------------------------------------------------

    async def get_vehicle_analysis(
        self,
        branch_id: int,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list:
        """통합 차량 분석 (기간 필터 여부에 따라 소스 자동 선택)

        기간 필터가 있으면 branch_reviews에서 직접 집계하고,
        없으면 car_model_tags 테이블을 사용합니다.
        """
        from repository.session import get_client

        client = await get_client()

        if start_date and end_date:
            return await self._get_vehicle_analysis_from_reviews(
                client, branch_id, start_date, end_date
            )

        return await self._get_vehicle_analysis_from_car_model_tags(client, branch_id)

    async def get_vehicle_tags_raw(self, branch_id: int) -> dict:
        """car_model_tags에서 차량별 태그 데이터 조회 (VehicleRankItem용)

        카테고리 정보를 포함하여 차량 카테고리 태그만 필터링합니다.

        Returns:
            dict: {car_model: {"total_positive": N, "total_negative": N, "total_count": N,
                   "tags": {tag_name: {"positive": N, "negative": N, "total": N, "category_name": str}}}}
        """
        from repository.session import get_client

        client = await get_client()
        try:
            result = await (
                client.table("car_model_tags")
                .select(
                    "car_model, positive_count, negative_count, total_count, tags(name, categories(name))"
                )
                .eq("branch_id", branch_id)
                .execute()
            )
        except Exception as e:
            logger.warning(f"차량 태그 raw 조회 실패 (branch_id={branch_id}): {e}")
            return {}

        if not result.data:
            return {}

        car_data: dict[str, dict] = {}
        for row in result.data:
            car_model = row.get("car_model", "기타")
            tag_info = row.get("tags") or {}
            tag_name = tag_info.get("name", "기타")
            cat_info = tag_info.get("categories") or {}
            cat_name = cat_info.get("name", "")
            positive = row.get("positive_count", 0)
            negative = row.get("negative_count", 0)
            total = row.get("total_count", 0)

            if car_model not in car_data:
                car_data[car_model] = {
                    "total_positive": 0,
                    "total_negative": 0,
                    "total_count": 0,
                    "tags": {},
                }
            car_data[car_model]["total_positive"] += positive
            car_data[car_model]["total_negative"] += negative
            car_data[car_model]["total_count"] += total
            car_data[car_model]["tags"][tag_name] = {
                "positive": positive,
                "negative": negative,
                "total": total,
                "category_name": cat_name,
            }

        return car_data

    def build_vehicle_rankings(
        self,
        vehicle_tags_raw: dict,
        vehicle_analysis: list,
    ) -> tuple:
        """차량별 호평/불만 Top 5 + 태그 리스트 생성

        vehicle_analysis (기간 필터링 된 데이터)의 count/like_ratio를 기본으로,
        vehicle_tags_raw (all-time car_model_tags)의 태그를 보강하여 VehicleRankItem 생성.

        Returns:
            (top_liked, top_disliked)
        """
        from services.report_service import VehicleRankItem

        va_map = {v.get("model", ""): v for v in vehicle_analysis}

        items: list[dict] = []
        for car_model, raw in vehicle_tags_raw.items():
            va = va_map.get(car_model, {})
            count = va.get("count", 0) or raw.get("total_count", 0)
            like_ratio = va.get("like_ratio", 0)
            dislike_ratio = va.get("dislike_ratio", 0)

            if not va and raw["total_count"] > 0:
                like_ratio = round(raw["total_positive"] / raw["total_count"] * 100)
                dislike_ratio = round(raw["total_negative"] / raw["total_count"] * 100)

            veh_tags = [
                (name, ts)
                for name, ts in raw.get("tags", {}).items()
                if ts.get("category_name", "") in VEHICLE_CATEGORIES
                and ts.get("total", 0) > 0
            ]

            pos_sorted = sorted(veh_tags, key=lambda x: x[1]["positive"], reverse=True)
            pos_tags = [
                f"{n}({ts['positive']}건)"
                for n, ts in pos_sorted[:3]
                if ts["positive"] > 0
            ]

            neg_sorted = sorted(veh_tags, key=lambda x: x[1]["negative"], reverse=True)
            neg_tags = [
                f"{n}({ts['negative']}건)"
                for n, ts in neg_sorted[:3]
                if ts["negative"] > 0
            ]

            total_pos_tags = sum(ts["positive"] for _, ts in veh_tags)
            total_neg_tags = sum(ts["negative"] for _, ts in veh_tags)

            items.append(
                {
                    "model": car_model,
                    "count": count,
                    "total_pos_tags": total_pos_tags,
                    "total_neg_tags": total_neg_tags,
                    "pos_tags": pos_tags,
                    "neg_tags": neg_tags,
                }
            )

        sorted_liked = sorted(
            items, key=lambda x: (x["total_pos_tags"], x["count"]), reverse=True
        )
        top_liked = [
            VehicleRankItem(
                model=it["model"],
                count=it["count"],
                ratio=it["total_pos_tags"],
                tags=it["pos_tags"],
            )
            for it in sorted_liked[:5]
        ]

        sorted_disliked = sorted(
            [it for it in items if it["total_neg_tags"] > 0],
            key=lambda x: (x["total_neg_tags"], x["count"]),
            reverse=True,
        )
        top_disliked = [
            VehicleRankItem(
                model=it["model"],
                count=it["count"],
                ratio=it["total_neg_tags"],
                tags=it["neg_tags"],
            )
            for it in sorted_disliked[:5]
        ]

        return top_liked, top_disliked

    # ----------------------------------------------------------------
    # 내부 메서드
    # ----------------------------------------------------------------

    async def _get_vehicle_analysis_from_car_model_tags(
        self, client, branch_id: int
    ) -> list:
        """car_model_tags 테이블에서 차량별 분석 데이터 조회 후 변환"""
        try:
            result = await (
                client.table("car_model_tags")
                .select(
                    "car_model, tag_id, positive_count, negative_count, neutral_count, total_count, tags(name)"
                )
                .eq("branch_id", branch_id)
                .execute()
            )
        except Exception as e:
            logger.warning(f"차량별 분석 조회 실패 (branch_id={branch_id}): {e}")
            return []

        if not result.data:
            return []

        car_data: dict[str, dict] = {}

        for row in result.data:
            car_model = row.get("car_model", "기타")
            tag_info = row.get("tags") or {}
            tag_name = tag_info.get("name", "기타")

            positive = row.get("positive_count", 0)
            negative = row.get("negative_count", 0)
            neutral = row.get("neutral_count", 0)
            total = row.get("total_count", 0)

            if car_model not in car_data:
                car_data[car_model] = {
                    "total_count": 0,
                    "total_positive": 0,
                    "total_negative": 0,
                    "tags": {},
                }

            car_data[car_model]["total_count"] += total
            car_data[car_model]["total_positive"] += positive
            car_data[car_model]["total_negative"] += negative
            car_data[car_model]["tags"][tag_name] = {
                "positive": positive,
                "negative": negative,
                "neutral": neutral,
                "total": total,
            }

        return self._convert_to_vehicle_analysis(car_data)

    async def _get_vehicle_analysis_from_reviews(
        self,
        client,
        branch_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> list:
        """branch_reviews에서 기간 필터링된 차량별 분석 (car_model_tags 대체)"""
        try:
            next_day = end_date + timedelta(days=1)

            all_rows: list[dict] = []
            batch_size = 1000
            offset = 0

            while True:
                result = await (
                    client.table("branch_reviews")
                    .select("car_model, sentiment")
                    .eq("branch_id", branch_id)
                    .gte("review_date", start_date.isoformat())
                    .lt("review_date", next_day.isoformat())
                    .range(offset, offset + batch_size - 1)
                    .execute()
                )
                if not result.data:
                    break
                all_rows.extend(result.data)
                if len(result.data) < batch_size:
                    break
                offset += batch_size

        except Exception as e:
            logger.warning(f"기간별 차량 분석 조회 실패 (branch_id={branch_id}): {e}")
            return []

        if not all_rows:
            return []

        # branch_reviews에는 태그 정보가 없으므로 car_model_tags에서 태그 보강
        tag_info = await self._get_vehicle_tag_info(client, branch_id)

        # 차량별 그룹화 (reviews 소스이므로 total_count = total, tags = tag_info에서)
        car_data: dict[str, dict] = {}
        for row in all_rows:
            car_model = row.get("car_model") or "기타"
            sentiment = row.get("sentiment", "neutral")

            if car_model not in car_data:
                car_data[car_model] = {
                    "total_count": 0,
                    "total_positive": 0,
                    "total_negative": 0,
                    "tags": tag_info.get(car_model, {}),
                }

            car_data[car_model]["total_count"] += 1
            if sentiment == "positive":
                car_data[car_model]["total_positive"] += 1
            elif sentiment == "negative":
                car_data[car_model]["total_negative"] += 1

        return self._convert_to_vehicle_analysis(car_data)

    async def _get_vehicle_tag_info(self, client, branch_id: int) -> dict:
        """car_model_tags에서 차량별 대표 태그 정보 조회 (기간 무관)

        top_praise, top_issue 계산에 필요한 태그 통계를 반환합니다.
        _convert_to_vehicle_analysis의 tags 구조와 호환되도록
        {"positive": N, "negative": N, "total": N} 형태로 반환합니다.

        Returns:
            dict: {car_model: {tag_name: {"positive": N, "negative": N, "total": N}}}
        """
        try:
            result = await (
                client.table("car_model_tags")
                .select(
                    "car_model, positive_count, negative_count, total_count, tags(name)"
                )
                .eq("branch_id", branch_id)
                .execute()
            )
        except Exception:
            return {}

        if not result.data:
            return {}

        car_tags: dict[str, dict] = {}
        for row in result.data:
            car_model = row.get("car_model", "기타")
            tag_info = row.get("tags") or {}
            tag_name = tag_info.get("name", "기타")

            if car_model not in car_tags:
                car_tags[car_model] = {}

            car_tags[car_model][tag_name] = {
                "positive": row.get("positive_count", 0),
                "negative": row.get("negative_count", 0),
                "total": row.get("total_count", 0),
            }

        return car_tags
