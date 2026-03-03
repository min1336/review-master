"""Step 8: monthly_rating_stats / monthly_sentiment_stats / monthly_tag_stats 저장"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from repository.orm_models import (
    MonthlyRatingStatsORM,
    MonthlySentimentStatsORM,
    MonthlyTagStatsORM,
    TagORM,
)
from schemas.dto import ProcessedReviewDTO

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class MonthlyStatsUpdater:
    """월별 통계 3개 테이블을 한 스텝에서 처리"""

    async def update(
        self, session: AsyncSession, processed: list[ProcessedReviewDTO]
    ) -> dict:
        rating_count = await self._update_rating_stats(session, processed)
        sentiment_count = await self._update_sentiment_stats(session, processed)
        tag_count = await self._update_tag_stats(session, processed)

        return {
            "rating_stats": rating_count,
            "sentiment_stats": sentiment_count,
            "tag_stats": tag_count,
        }

    # ------------------------------------------------------------------
    # 4a. monthly_rating_stats
    # ------------------------------------------------------------------
    async def _update_rating_stats(
        self, session: AsyncSession, processed: list[ProcessedReviewDTO]
    ) -> int:
        """(branch_id, period) 그룹핑 -> 평점 평균 계산 -> upsert"""
        # 메모리 집계: (branch_id, period) -> {sum_service, sum_car, sum_conv, count}
        groups: dict[tuple[int, str], dict] = {}

        for pr in processed:
            period = self._get_period(pr)
            if not period:
                continue
            key = (pr.branch_id, period)
            if key not in groups:
                groups[key] = {
                    "sum_service": 0.0, "cnt_service": 0,
                    "sum_car": 0.0, "cnt_car": 0,
                    "sum_convenience": 0.0, "cnt_convenience": 0,
                    "review_count": 0,
                }
            g = groups[key]
            g["review_count"] += 1
            if pr.review.rating is not None:
                g["sum_service"] += pr.review.rating
                g["cnt_service"] += 1
            if pr.rating_car is not None:
                g["sum_car"] += pr.rating_car
                g["cnt_car"] += 1
            if pr.rating_convenience is not None:
                g["sum_convenience"] += pr.rating_convenience
                g["cnt_convenience"] += 1

        if not groups:
            return 0

        # 기존 데이터 조회 -> 증분 합산
        saved = 0
        for (branch_id, period), g in groups.items():
            try:
                async with session.begin_nested():
                    result = await session.execute(
                        select(MonthlyRatingStatsORM)
                        .where(MonthlyRatingStatsORM.branch_id == branch_id)
                        .where(MonthlyRatingStatsORM.period == period)
                    )
                    existing_row = result.scalar_one_or_none()
                    old: dict = {}
                    if existing_row:
                        old = {
                            c.key: getattr(existing_row, c.key)
                            for c in MonthlyRatingStatsORM.__table__.columns
                        }

                    old_review_count = old.get("review_count", 0) or 0
                    new_review_count = old_review_count + g["review_count"]

                    avg_service = self._incremental_avg(
                        old.get("avg_rating_service"), old_review_count,
                        g["sum_service"], g["cnt_service"],
                    )
                    avg_car = self._incremental_avg(
                        old.get("avg_rating_car"), old_review_count,
                        g["sum_car"], g["cnt_car"],
                    )
                    avg_conv = self._incremental_avg(
                        old.get("avg_rating_convenience"), old_review_count,
                        g["sum_convenience"], g["cnt_convenience"],
                    )

                    values = {
                        "branch_id": branch_id,
                        "period": period,
                        "avg_rating_service": avg_service,
                        "avg_rating_car": avg_car,
                        "avg_rating_convenience": avg_conv,
                        "review_count": new_review_count,
                    }
                    stmt = (
                        pg_insert(MonthlyRatingStatsORM.__table__)
                        .values(**values)
                        .on_conflict_do_update(
                            index_elements=["branch_id", "period"],
                            set_={
                                "avg_rating_service": values["avg_rating_service"],
                                "avg_rating_car": values["avg_rating_car"],
                                "avg_rating_convenience": values["avg_rating_convenience"],
                                "review_count": values["review_count"],
                            },
                        )
                    )
                    await session.execute(stmt)
                saved += 1
            except Exception as e:
                logger.warning(
                    f"monthly_rating_stats upsert 실패 (branch={branch_id}, period={period}): {e}"
                )

        logger.info(f"monthly_rating_stats 저장 완료: {saved}건")
        return saved

    # ------------------------------------------------------------------
    # 4b. monthly_sentiment_stats
    # ------------------------------------------------------------------
    async def _update_sentiment_stats(
        self, session: AsyncSession, processed: list[ProcessedReviewDTO]
    ) -> int:
        """(branch_id, period) 그룹핑 -> positive/negative/neutral 카운트 -> upsert"""
        groups: dict[tuple[int, str], dict[str, int]] = {}

        for pr in processed:
            period = self._get_period(pr)
            if not period:
                continue
            key = (pr.branch_id, period)
            if key not in groups:
                groups[key] = {"positive": 0, "negative": 0, "neutral": 0}
            sentiment = pr.sentiment if pr.sentiment in ("positive", "negative", "neutral") else "neutral"
            groups[key][sentiment] += 1

        if not groups:
            return 0

        saved = 0
        for (branch_id, period), counts in groups.items():
            try:
                async with session.begin_nested():
                    result = await session.execute(
                        select(MonthlySentimentStatsORM)
                        .where(MonthlySentimentStatsORM.branch_id == branch_id)
                        .where(MonthlySentimentStatsORM.period == period)
                    )
                    existing_row = result.scalar_one_or_none()
                    old: dict = {}
                    if existing_row:
                        old = {
                            c.key: getattr(existing_row, c.key)
                            for c in MonthlySentimentStatsORM.__table__.columns
                        }

                    new_pos = (old.get("positive_count", 0) or 0) + counts["positive"]
                    new_neg = (old.get("negative_count", 0) or 0) + counts["negative"]
                    new_neu = (old.get("neutral_count", 0) or 0) + counts["neutral"]
                    total = new_pos + new_neg + new_neu

                    values = {
                        "branch_id": branch_id,
                        "period": period,
                        "positive_count": new_pos,
                        "negative_count": new_neg,
                        "neutral_count": new_neu,
                        "review_count": total,
                    }
                    stmt = (
                        pg_insert(MonthlySentimentStatsORM.__table__)
                        .values(**values)
                        .on_conflict_do_update(
                            index_elements=["branch_id", "period"],
                            set_={
                                "positive_count": values["positive_count"],
                                "negative_count": values["negative_count"],
                                "neutral_count": values["neutral_count"],
                                "review_count": values["review_count"],
                            },
                        )
                    )
                    await session.execute(stmt)
                saved += 1
            except Exception as e:
                logger.warning(
                    f"monthly_sentiment_stats upsert 실패 (branch={branch_id}, period={period}): {e}"
                )

        logger.info(f"monthly_sentiment_stats 저장 완료: {saved}건")
        return saved

    # ------------------------------------------------------------------
    # 4c. monthly_tag_stats
    # ------------------------------------------------------------------
    async def _update_tag_stats(
        self, session: AsyncSession, processed: list[ProcessedReviewDTO]
    ) -> int:
        """(branch_id, period, tag_name) 그룹핑 -> 감정 카운트 -> upsert"""
        groups: dict[tuple[int, str, str], dict[str, int]] = {}

        for pr in processed:
            period = self._get_period(pr)
            if not period:
                continue
            for tag_name, sentiments in pr.tag_sentiments.items():
                if tag_name == "기타":
                    continue
                key = (pr.branch_id, period, tag_name)
                if key not in groups:
                    groups[key] = {"positive": 0, "negative": 0, "neutral": 0}
                g = groups[key]
                g["positive"] += len(sentiments.get("positive", []))
                g["negative"] += len(sentiments.get("negative", []))
                g["neutral"] += len(sentiments.get("neutral", []))

        if not groups:
            return 0

        # tag_name -> tag_id 일괄 변환
        all_tag_names = {k[2] for k in groups}
        tag_id_cache: dict[str, int] = {}
        try:
            result = await session.execute(
                select(TagORM.id, TagORM.name)
                .where(TagORM.name.in_(list(all_tag_names)))
            )
            for row in result.all():
                tag_id_cache[row.name] = row.id
        except Exception as e:
            logger.warning(f"tags 배치 조회 실패: {e}")
            return 0

        saved = 0
        for (branch_id, period, tag_name), counts in groups.items():
            tag_id = tag_id_cache.get(tag_name)
            if not tag_id:
                continue
            try:
                async with session.begin_nested():
                    result = await session.execute(
                        select(MonthlyTagStatsORM)
                        .where(MonthlyTagStatsORM.branch_id == branch_id)
                        .where(MonthlyTagStatsORM.period == period)
                        .where(MonthlyTagStatsORM.tag_id == tag_id)
                    )
                    existing_row = result.scalar_one_or_none()
                    old: dict = {}
                    if existing_row:
                        old = {
                            c.key: getattr(existing_row, c.key)
                            for c in MonthlyTagStatsORM.__table__.columns
                        }

                    new_pos = (old.get("positive_count", 0) or 0) + counts["positive"]
                    new_neg = (old.get("negative_count", 0) or 0) + counts["negative"]
                    new_neu = (old.get("neutral_count", 0) or 0) + counts["neutral"]

                    values = {
                        "branch_id": branch_id,
                        "period": period,
                        "tag_id": tag_id,
                        "positive_count": new_pos,
                        "negative_count": new_neg,
                        "neutral_count": new_neu,
                    }
                    stmt = (
                        pg_insert(MonthlyTagStatsORM.__table__)
                        .values(**values)
                        .on_conflict_do_update(
                            index_elements=["branch_id", "period", "tag_id"],
                            set_={
                                "positive_count": values["positive_count"],
                                "negative_count": values["negative_count"],
                                "neutral_count": values["neutral_count"],
                            },
                        )
                    )
                    await session.execute(stmt)
                saved += 1
            except Exception as e:
                logger.warning(
                    f"monthly_tag_stats upsert 실패 (branch={branch_id}, period={period}, tag={tag_name}): {e}"
                )

        logger.info(f"monthly_tag_stats 저장 완료: {saved}건")
        return saved

    # ------------------------------------------------------------------
    # 유틸리티
    # ------------------------------------------------------------------
    @staticmethod
    def _get_period(pr: ProcessedReviewDTO) -> str | None:
        """리뷰의 created_at에서 YYYY-MM 형식 period 추출"""
        if pr.review.created_at:
            return pr.review.created_at.strftime("%Y-%m")
        return None

    @staticmethod
    def _incremental_avg(
        old_avg: float | None, old_count: int,
        new_sum: float, new_count: int,
    ) -> float | None:
        """기존 평균 + 새 합계로 증분 평균 계산"""
        if new_count == 0 and (old_avg is None or old_count == 0):
            return None
        old_total = (old_avg or 0.0) * old_count
        total_sum = old_total + new_sum
        total_count = old_count + new_count
        if total_count == 0:
            return None
        return round(total_sum / total_count, 2)
