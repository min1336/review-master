"""차량 분석 서비스

차량별 태그 데이터 조회 및 순위 산출을 담당합니다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.analysis.patterns import VEHICLE_CATEGORIES
from repository.orm_models import BranchReviewORM, CategoryORM

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
        없으면 monthly_car_model_tag_stats에서 집계합니다.
        """
        from repository.database import get_session_factory

        async with get_session_factory()() as session:
            if start_date and end_date:
                return await self._get_vehicle_analysis_from_reviews(
                    session, branch_id, start_date, end_date
                )

            return await self._get_vehicle_analysis_from_monthly_stats(branch_id)

    async def get_vehicle_tags_raw(
        self,
        branch_id: int,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict:
        """monthly_car_model_tag_stats에서 차량별 태그 데이터 조회 (VehicleRankItem용)

        카테고리 정보를 포함하여 차량 카테고리 태그만 필터링합니다.

        Args:
            start_date: 시작일. None이면 전 기간.
            end_date: 종료일. None이면 전 기간.

        Returns:
            dict: {car_model: {"total_positive": N, "total_negative": N, "total_count": N,
                   "tags": {tag_name: {"positive": N, "negative": N, "total": N, "category_name": str}}}}
        """
        from repository.car_model_repository import CarModelRepository
        from repository.database import get_session_factory

        period_from = start_date.strftime("%Y-%m") if start_date else None
        period_to = end_date.strftime("%Y-%m") if end_date else None

        async with get_session_factory()() as session:
            try:
                repo = CarModelRepository(session)
                return await repo.get_vehicle_tags_raw(
                    branch_id, period_from=period_from, period_to=period_to
                )
            except Exception as e:
                logger.warning("차량 태그 raw 조회 실패 (branch_id=%s): %s", branch_id, e)
                return {}

    def build_vehicle_rankings(
        self,
        vehicle_tags_raw: dict,
        vehicle_analysis: list,
    ) -> tuple:
        """차량별 호평/불만 Top 5 + 태그 리스트 생성

        vehicle_analysis (기간 필터링 된 실제 모델명 데이터)를 기본으로,
        vehicle_tags_raw (car_model_tags)의 태그가 매칭되면 보강합니다.

        vehicle_tags_raw의 키가 차종 카테고리(SUV, 준중형 등)일 경우
        vehicle_analysis의 실제 모델명을 우선 사용합니다.

        Returns:
            (top_liked, top_disliked)
        """
        _CAR_TYPE_CATEGORIES = {"경형", "소형", "준중형", "중형", "대형", "SUV", "RV", "수입"}
        raw_keys = set(vehicle_tags_raw.keys())
        raw_is_category = raw_keys and raw_keys.issubset(_CAR_TYPE_CATEGORIES)

        if raw_is_category or not vehicle_tags_raw:
            items = self._build_items_from_analysis(vehicle_analysis)
        else:
            items = self._build_items_from_raw(vehicle_tags_raw, vehicle_analysis)

        top_liked = self._pick_top_liked(items)
        top_disliked = self._pick_top_disliked(items)

        return top_liked, top_disliked

    # ----------------------------------------------------------------
    # 랭킹 빌더 헬퍼
    # ----------------------------------------------------------------

    def _build_items_from_analysis(self, vehicle_analysis: list) -> list[dict]:
        """vehicle_analysis만으로 랭킹 아이템 빌드 (raw가 카테고리 키이거나 없을 때)"""
        items: list[dict] = []

        for va in vehicle_analysis:
            model = va.get("model", "") if isinstance(va, dict) else getattr(va, "model", "")
            count = va.get("count", 0) if isinstance(va, dict) else getattr(va, "count", 0)
            like_ratio = va.get("like_ratio", 0) if isinstance(va, dict) else getattr(va, "like_ratio", 0)
            dislike_ratio = va.get("dislike_ratio", 0) if isinstance(va, dict) else getattr(va, "dislike_ratio", 0)
            top_praise = va.get("top_praise", "") if isinstance(va, dict) else getattr(va, "top_praise", "")
            top_issue = va.get("top_issue", "") if isinstance(va, dict) else getattr(va, "top_issue", "")

            if not model or count == 0:
                continue

            pos_tags = [top_praise] if top_praise else []
            neg_tags = [top_issue] if top_issue else []
            total_pos = count * like_ratio // 100 if like_ratio else 0
            total_neg = count * dislike_ratio // 100 if dislike_ratio else 0

            items.append({
                "model": model,
                "count": count,
                "total_pos_tags": total_pos,
                "total_neg_tags": total_neg,
                "pos_tags": pos_tags,
                "neg_tags": neg_tags,
            })

        return items

    def _build_items_from_raw(self, vehicle_tags_raw: dict, vehicle_analysis: list) -> list[dict]:
        """vehicle_tags_raw(실제 모델명 키)와 vehicle_analysis를 병합하여 랭킹 아이템 빌드"""
        items: list[dict] = []
        va_map = {v.get("model", ""): v for v in vehicle_analysis}

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

            subtag_entries = [(n, ts) for n, ts in veh_tags if n != ts.get("category_name")]
            display_tags = subtag_entries if subtag_entries else veh_tags

            pos_sorted = sorted(
                [(name, ts["positive"]) for name, ts in display_tags if ts["positive"] > 0],
                key=lambda x: x[1], reverse=True,
            )
            neg_sorted = sorted(
                [(name, ts["negative"]) for name, ts in display_tags if ts["negative"] > 0],
                key=lambda x: x[1], reverse=True,
            )

            pos_tags = [f"{name}({cnt}건)" for name, cnt in pos_sorted[:2]]
            neg_tags = [f"{name}({cnt}건)" for name, cnt in neg_sorted[:2]]

            items.append({
                "model": car_model,
                "count": count,
                "total_pos_tags": sum(cnt for _, cnt in pos_sorted),
                "total_neg_tags": sum(cnt for _, cnt in neg_sorted),
                "pos_tags": pos_tags,
                "neg_tags": neg_tags,
            })

        return items

    def _pick_top_liked(self, items: list[dict]) -> list:
        """호평 Top 5 VehicleRankItem 리스트 반환"""
        from services.report_service import VehicleRankItem

        sorted_liked = sorted(
            items, key=lambda x: (x["total_pos_tags"], x["count"]), reverse=True
        )
        return [
            VehicleRankItem(
                model=it["model"],
                count=it["count"],
                ratio=it["total_pos_tags"],
                tags=it["pos_tags"],
            )
            for it in sorted_liked[:5]
        ]

    def _pick_top_disliked(self, items: list[dict]) -> list:
        """불만 Top 5 VehicleRankItem 리스트 반환"""
        # 순환 참조 방지를 위해 함수 내부에서 import
        from services.report_service import VehicleRankItem

        sorted_disliked = sorted(
            [it for it in items if it["total_neg_tags"] > 0],
            key=lambda x: (x["total_neg_tags"], x["count"]),
            reverse=True,
        )
        return [
            VehicleRankItem(
                model=it["model"],
                count=it["count"],
                ratio=it["total_neg_tags"],
                tags=it["neg_tags"],
            )
            for it in sorted_disliked[:5]
        ]

    # ----------------------------------------------------------------
    # 내부 메서드
    # ----------------------------------------------------------------

    async def _get_vehicle_analysis_from_monthly_stats(
        self, branch_id: int,
    ) -> list:
        """monthly_car_model_tag_stats에서 차량별 분석 데이터 조회 후 변환"""
        from repository.car_model_repository import CarModelRepository
        from repository.database import get_session_factory

        async with get_session_factory()() as session:
            try:
                repo = CarModelRepository(session)
                car_data = await repo.get_vehicle_analysis_data(branch_id)
            except Exception as e:
                logger.warning("차량별 분석 조회 실패 (branch_id=%s): %s", branch_id, e)
                return []

        if not car_data:
            return []

        return self._convert_to_vehicle_analysis(car_data)

    async def _get_vehicle_analysis_from_reviews(
        self,
        session: AsyncSession,
        branch_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> list:
        """branch_reviews에서 기간 필터링된 차량별 분석 (car_model_tags 대체)"""
        try:
            next_day = end_date + timedelta(days=1)

            all_rows: list[tuple] = []
            batch_size = 1000
            offset = 0

            while True:
                stmt = (
                    select(BranchReviewORM.car_model, BranchReviewORM.sentiment)
                    .where(BranchReviewORM.branch_id == branch_id)
                    .where(BranchReviewORM.review_date >= start_date)
                    .where(BranchReviewORM.review_date < next_day)
                    .offset(offset)
                    .limit(batch_size)
                )
                result = await session.execute(stmt)
                rows = result.all()
                if not rows:
                    break
                all_rows.extend(rows)
                if len(rows) < batch_size:
                    break
                offset += batch_size

        except Exception as e:
            logger.warning("기간별 차량 분석 조회 실패 (branch_id=%s): %s", branch_id, e)
            return []

        if not all_rows:
            return []

        # review_tag_mappings에서 차량 모델별 태그 직접 조회
        tag_info = await self._get_vehicle_tag_info_from_reviews(
            session, branch_id, start_date, end_date
        )

        # 차량별 그룹화
        car_data: dict[str, dict] = {}
        for row in all_rows:
            car_model = row.car_model or "기타"
            sentiment = row.sentiment or "neutral"

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

    async def _get_vehicle_tag_info_from_reviews(
        self,
        session: AsyncSession,
        branch_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> dict:
        """review_tag_mappings에서 차량 모델별 태그 정보 직접 조회

        car_models_master를 경유하지 않고 review_tag_mappings + branch_reviews를
        직접 조인하여 실제 모델명 기준으로 태그 통계를 반환합니다.

        Returns:
            dict: {car_model: {tag_name: {"positive": N, "negative": N, "total": N}}}
        """
        from repository.orm_models import ReviewTagMappingORM, TagORM

        next_day = end_date + timedelta(days=1)

        try:
            stmt = (
                select(
                    BranchReviewORM.car_model,
                    TagORM.name.label("tag_name"),
                    ReviewTagMappingORM.sentiment,
                    func.count().label("cnt"),
                )
                .join(BranchReviewORM, BranchReviewORM.review_id == ReviewTagMappingORM.review_id)
                .join(TagORM, TagORM.id == ReviewTagMappingORM.tag_id)
                .where(BranchReviewORM.branch_id == branch_id)
                .where(BranchReviewORM.review_date >= start_date)
                .where(BranchReviewORM.review_date < next_day)
                .where(TagORM.category_id.in_(
                    select(CategoryORM.id).where(CategoryORM.name.in_(VEHICLE_CATEGORIES))
                ))
                .group_by(
                    BranchReviewORM.car_model,
                    TagORM.name,
                    ReviewTagMappingORM.sentiment,
                )
            )
            result = await session.execute(stmt)
            rows = result.all()
        except Exception as e:
            logger.warning("차량 태그 직접 조회 실패 (branch_id=%s): %s", branch_id, e)
            return {}

        car_tags: dict[str, dict] = {}
        for row in rows:
            car_model = row.car_model or "기타"
            tag_name = row.tag_name
            sentiment = row.sentiment
            cnt = row.cnt

            if car_model not in car_tags:
                car_tags[car_model] = {}
            if tag_name not in car_tags[car_model]:
                car_tags[car_model][tag_name] = {"positive": 0, "negative": 0, "total": 0}

            if sentiment == "positive":
                car_tags[car_model][tag_name]["positive"] += cnt
            elif sentiment == "negative":
                car_tags[car_model][tag_name]["negative"] += cnt
            car_tags[car_model][tag_name]["total"] += cnt

        return car_tags

