"""요약 비즈니스 로직

조회/수정 + 승인/거절 로직을 담당.
AI 요약 생성은 summary_generator.py로 분리됨.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from core.timezone import utc_now
from repository.orm_models import BranchReviewORM
from schemas.dto import (
    BranchCarModelsDTO,
    BranchReviewsDTO,
    CarModelDTO,
    CarModelTagDTO,
    PendingSummaryResultDTO,
    RegionStatsDTO,
    SummaryStatsDTO,
)

if TYPE_CHECKING:
    from infrastructure.athena_client import AthenaClient
    from repository.branch_tag_repository import BranchTagRepository
    from repository.review_repository import BranchReviewRepository
    from repository.review_repository import SentimentRepository
    from repository.summary_repository import SummaryRepository

logger = logging.getLogger(__name__)


class SummaryService:
    """요약 비즈니스 로직 (조회/수정/승인)"""

    def __init__(
        self,
        summary_repo: SummaryRepository,
        branch_tag_repo: BranchTagRepository,
        review_repo: BranchReviewRepository,
        sentiment_repo: SentimentRepository | None = None,
        athena_client: AthenaClient | None = None,
    ):
        self.summary_repo = summary_repo
        self.branch_tag_repo = branch_tag_repo
        self.review_repo = review_repo
        self.sentiment_repo = sentiment_repo
        self.athena_client = athena_client

        # AI 생성은 SummaryGenerator로 위임
        from services.summary_generator import SummaryGenerator
        self._generator = SummaryGenerator(
            summary_repo, branch_tag_repo, review_repo, sentiment_repo, athena_client,
        )

    # ============================================================
    # 조회 / 수정
    # ============================================================

    async def get_summary_by_branch_id(self, branch_id: int) -> dict | None:
        """지점 ID로 요약 조회 (Public API용)"""
        return await self.summary_repo.get_by_branch_id(branch_id)

    @staticmethod
    def pick_latest_summary(summary) -> str | None:
        """요약 문자열 선택 (가장 최신/짧은 기간 우선)"""
        candidates = [
            summary.summary_1m,
            summary.summary_3m,
            summary.summary_6m,
            summary.summary_1y,
            summary.summary_all,
        ]
        for value in candidates:
            if value and str(value).strip():
                return value
        return None

    async def get_summaries(
        self,
        region: str | None = None,
        region_group: str | None = None,
        keyword: str | None = None,
        min_rating: float | None = None,
        max_rating: float | None = None,
        min_reviews: int = 0,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "branch_id",
        order: str = "asc",
        review_date_from: datetime | None = None,
        review_date_to: datetime | None = None,
    ) -> list[dict]:
        """요약 목록 조회 (날짜 범위 필터링 지원)"""
        branch_ids_filter = None
        if review_date_from or review_date_to:
            branch_ids_filter = await self.summary_repo.get_branch_ids_by_date_range(
                review_date_from=review_date_from, review_date_to=review_date_to
            )

            if not branch_ids_filter:
                logger.info(
                    "날짜 필터 결과 없음: %s ~ %s", review_date_from, review_date_to
                )
                return []

        if keyword or min_rating or max_rating:
            summaries = await self.summary_repo.search(
                keyword=keyword,
                region=region,
                region_group=region_group,
                min_rating=min_rating,
                max_rating=max_rating,
                min_reviews=min_reviews,
                limit=limit,
            )
            if branch_ids_filter is not None:
                summaries = [s for s in summaries if s.branch_id in branch_ids_filter]
        else:
            summaries = await self.summary_repo.get_all_with_filters(
                region=region,
                region_group=region_group,
                min_reviews=min_reviews,
                limit=limit,
                offset=offset,
                sort_by=sort_by,
                order=order,
                branch_ids=branch_ids_filter,
            )

        return [s.model_dump() if hasattr(s, "model_dump") else s for s in summaries]

    async def get_summary(self, branch_id: int) -> dict | None:
        """단일 요약 조회"""
        summary = await self.summary_repo.get_by_branch_id(branch_id)
        return summary.model_dump() if summary else None

    async def update_summary(self, branch_id: int, data: dict) -> dict | None:
        """요약 수정"""
        data["branch_id"] = branch_id
        result = await self.summary_repo.upsert_by_branch_id(data)
        return result.model_dump() if result else None

    async def get_stats(self) -> SummaryStatsDTO:
        """통계 조회"""
        return await self.summary_repo.get_stats()

    async def get_region_stats(self) -> list[RegionStatsDTO]:
        """지역별 통계"""
        data = await self.summary_repo.get_region_data()

        if not data:
            return []

        region_stats = {}
        for row in data:
            region = row.get("region") or "미분류"
            city = region.split()[0] if region and region.strip() else "미분류"

            if city not in region_stats:
                region_stats[city] = {
                    "region": city,
                    "count": 0,
                    "total_reviews": 0,
                    "rating_sum": 0,
                    "rating_count": 0,
                }

            region_stats[city]["count"] += 1
            region_stats[city]["total_reviews"] += row.get("review_count") or 0

            if row.get("avg_rating"):
                region_stats[city]["rating_sum"] += float(row["avg_rating"])
                region_stats[city]["rating_count"] += 1

        stats_list = []
        for city, stats in region_stats.items():
            avg_rating = 0
            if stats["rating_count"] > 0:
                avg_rating = round(stats["rating_sum"] / stats["rating_count"], 2)

            stats_list.append(
                RegionStatsDTO(
                    region=city,
                    count=stats["count"],
                    avg_rating=avg_rating,
                    total_reviews=stats["total_reviews"],
                )
            )

        stats_list.sort(key=lambda x: x.count, reverse=True)
        return stats_list

    async def get_branch_reviews(
        self,
        branch_id: int,
        car_model: str | None = None,
        sentiment: str | None = None,
        review_date_from: datetime | None = None,
        review_date_to: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> BranchReviewsDTO:
        """지점별 원본 리뷰 목록 조회 (Athena primary, Supabase fallback)"""
        use_athena = (
            self.athena_client is not None
            and car_model is None
            and sentiment is None
        )

        if use_athena:
            try:
                result = await self._get_branch_reviews_via_athena(
                    branch_id, review_date_from, review_date_to, limit, offset
                )
                result.car_models = await self.review_repo.get_distinct_car_models(branch_id)
                return result
            except Exception as e:
                logger.warning("Athena 리뷰 조회 실패, Supabase 폴백: %s", e)

        return await self.review_repo.get_by_branch(
            branch_id=branch_id,
            car_model=car_model,
            sentiment=sentiment,
            review_date_from=review_date_from,
            review_date_to=review_date_to,
            limit=limit,
            offset=offset,
        )

    async def _get_branch_reviews_via_athena(
        self,
        branch_id: int,
        review_date_from: datetime | None,
        review_date_to: datetime | None,
        limit: int,
        offset: int,
    ) -> BranchReviewsDTO:
        """Athena에서 리뷰 조회 + Supabase sentiment 병합"""
        date_from = review_date_from.strftime("%Y-%m-%d") if review_date_from else None
        date_to = review_date_to.strftime("%Y-%m-%d") if review_date_to else None

        rows, total = await asyncio.to_thread(
            self.athena_client.fetch_reviews_by_branch,
            branch_id=branch_id,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )

        review_ids = [int(r["review_id"]) for r in rows if r.get("review_id")]
        if review_ids:
            sentiment_map = await self.review_repo.get_sentiments_by_review_ids(review_ids)
            for row in rows:
                rid = int(row["review_id"]) if row.get("review_id") else None
                if rid and rid in sentiment_map:
                    row["sentiment"] = sentiment_map[rid]

        return BranchReviewsDTO(reviews=rows, total=total)

    async def get_car_model_tags(
        self,
        branch_id: int,
        car_model: str | None = None,
    ) -> BranchCarModelsDTO:
        """지점별 차량 모델 태그 분석"""
        from repository.car_model_repository import CarModelRepository
        from repository.database import get_session_factory

        async with get_session_factory()() as session:
            repo = CarModelRepository(session)

            try:
                rows = await repo.get_car_model_tags(branch_id, car_model)
            except Exception as e:
                logger.warning("차량 태그 조회 실패 (branch_id=%s): %s", branch_id, e)
                return BranchCarModelsDTO(branch_id=branch_id, car_models=[])

            if not rows:
                return BranchCarModelsDTO(branch_id=branch_id, car_models=[])

            car_data: dict[str, dict] = {}
            for row in rows:
                car = row["car_model"]
                tag_name = row.get("tag_name", "기타")

                if car not in car_data:
                    car_data[car] = {"name": car, "tags": {}, "review_count": 0}

                car_data[car]["tags"][tag_name] = {
                    "name": tag_name,
                    "positive": row.get("positive_count", 0),
                    "negative": row.get("negative_count", 0),
                    "neutral": row.get("neutral_count", 0),
                    "total": row.get("total_count", 0),
                }

            for car in car_data:
                try:
                    count_result = await session.execute(
                        select(func.count())
                        .select_from(BranchReviewORM)
                        .where(BranchReviewORM.branch_id == branch_id)
                        .where(BranchReviewORM.car_model == car)
                    )
                    car_data[car]["review_count"] = count_result.scalar_one() or 0
                except Exception:
                    car_data[car]["review_count"] = 0

        car_models_dto: list[CarModelDTO] = []
        for car, data in sorted(car_data.items()):
            tags_dto = sorted(
                [
                    CarModelTagDTO(
                        name=tag_data["name"],
                        positive=tag_data["positive"],
                        negative=tag_data["negative"],
                        neutral=tag_data["neutral"],
                        total=tag_data["total"],
                    )
                    for tag_data in data["tags"].values()
                ],
                key=lambda x: x.total,
                reverse=True,
            )

            car_models_dto.append(
                CarModelDTO(
                    name=data["name"],
                    review_count=data.get("review_count", 0),
                    tags=tags_dto,
                )
            )

        return BranchCarModelsDTO(branch_id=branch_id, car_models=car_models_dto)

    # ============================================================
    # AI 요약 생성 (SummaryGenerator로 위임)
    # ============================================================

    async def generate_summary_with_data(
        self,
        branch_id: int,
        save_to_db: bool = True,
        mode: str = "marketing",
    ) -> dict:
        """태그+감정+리뷰 데이터를 활용한 AI 요약 생성"""
        return await self._generator.generate_summary_with_data(
            branch_id, save_to_db, mode
        )

    async def generate_pending_summary(
        self,
        branch_id: int,
        period: str = "1m",
    ) -> dict:
        """AI 요약을 생성하여 pending_summaries에 저장 (승인 대기 상태)"""
        return await self._generator.generate_pending_summary(branch_id, period)

    # ============================================================
    # 승인 / 거절
    # ============================================================

    async def get_pending_summaries(self, limit: int = 50) -> list[dict]:
        """승인 대기 중인 요약 목록 조회"""
        return await self.summary_repo.get_pending_summaries(limit)

    async def get_history(self, branch_id: int, limit: int = 10) -> list[dict]:
        """요약 변경 히스토리 조회"""
        return await self.summary_repo.get_history(branch_id, limit)

    async def approve_pending_summary(self, branch_id: int) -> dict | None:
        """대기 중인 요약 승인"""
        return await self.summary_repo.approve_pending_summary(branch_id)

    async def reject_pending_summary(self, branch_id: int) -> dict | None:
        """대기 중인 요약 거부"""
        return await self.summary_repo.reject_pending_summary(branch_id)

    async def apply_pending_summary(
        self, branch_id: int, period: str
    ) -> PendingSummaryResultDTO:
        """대기 중인 요약을 적용 (pending -> main)"""
        summary = await self.summary_repo.get_by_branch_id(branch_id)
        if not summary:
            raise ValueError(f"지점 {branch_id}을(를) 찾을 수 없습니다")

        summary_data = summary.model_dump()
        pending = summary_data.get("pending_summaries") or {}

        if period not in pending:
            raise ValueError(f"대기 중인 {period} 요약이 없습니다")

        field_map = {
            "all": "summary_all",
            "1y": "summary_1y",
            "6m": "summary_6m",
            "3m": "summary_3m",
            "1m": "summary_1m",
        }

        new_summary = pending.pop(period)

        await self.summary_repo.upsert_by_branch_id(
            {
                "branch_id": branch_id,
                field_map[period]: new_summary,
                "pending_summaries": pending,
            }
        )

        return PendingSummaryResultDTO(period=period, applied=new_summary)

    async def discard_pending_summary(
        self, branch_id: int, period: str
    ) -> PendingSummaryResultDTO:
        """대기 중인 요약 취소 (삭제)"""
        summary = await self.summary_repo.get_by_branch_id(branch_id)
        if not summary:
            raise ValueError(f"지점 {branch_id}을(를) 찾을 수 없습니다")

        summary_data = summary.model_dump()
        pending = summary_data.get("pending_summaries") or {}

        if period in pending:
            del pending[period]
            await self.summary_repo.upsert_by_branch_id(
                {"branch_id": branch_id, "pending_summaries": pending}
            )

        return PendingSummaryResultDTO(period=period, discarded=period)
