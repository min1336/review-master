from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.timezone import utc_now
from repository.orm_models import (
    BranchReviewORM,
    CategoryORM,
    MonthlyTagStatsORM,
    TagORM,
)

from schemas.dto import (
    BranchCarModelsDTO,
    BranchDetailDTO,
    BranchReviewsDTO,
    CarModelDTO,
    CarModelTagDTO,
    PendingSummaryResultDTO,
    RatingDistributionDTO,
    RatingStatsDTO,
    RegionStatsDTO,
    ReviewOutputDTO,
    SummariesOutputDTO,
    SummaryStatsDTO,
    SummaryWithTagsDTO,
    TagSentimentCountDTO,
)

logger = logging.getLogger(__name__)


class SummaryService:
    """요약 비즈니스 로직"""

    # 기간별 설정 (우선순위 순서)
    PERIOD_CONFIGS = [
        {"key": "1m", "field": "summary_1m", "months": 1, "label": "최근 1개월"},
        {"key": "3m", "field": "summary_3m", "months": 3, "label": "최근 3개월"},
        {"key": "6m", "field": "summary_6m", "months": 6, "label": "최근 6개월"},
        {"key": "1y", "field": "summary_1y", "months": 12, "label": "최근 1년"},
    ]
    MIN_REVIEWS_FOR_SUMMARY = 30

    def __init__(self, summary_repo, branch_tag_repo, review_repo, sentiment_repo=None, athena_client=None):
        self.summary_repo = summary_repo
        self.branch_tag_repo = branch_tag_repo
        self.review_repo = review_repo
        self.sentiment_repo = sentiment_repo
        self.athena_client = athena_client

    # ================================================================
    # Repository 래핑 메서드 (레이어드 아키텍처 준수)
    # ================================================================

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

    # ================================================================
    # 비즈니스 로직
    # ================================================================

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
        """
        요약 목록 조회 (날짜 범위 필터링 지원)
        """
        import logging

        # 날짜 필터가 있으면 해당 기간에 리뷰가 있는 지점만 조회
        branch_ids_filter = None
        if review_date_from or review_date_to:
            branch_ids_filter = await self.summary_repo.get_branch_ids_by_date_range(
                review_date_from=review_date_from, review_date_to=review_date_to
            )

            if not branch_ids_filter:
                logging.info(
                    f"날짜 필터 결과 없음: {review_date_from} ~ {review_date_to}"
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
            )
            if branch_ids_filter is not None:
                summaries = [s for s in summaries if s.branch_id in branch_ids_filter]

        return [s.model_dump() if hasattr(s, "model_dump") else s for s in summaries]

    async def get_summary(self, branch_id: int) -> dict | None:
        """단일 요약 조회"""
        summary = await self.summary_repo.get_by_branch_id(branch_id)
        return summary.model_dump() if summary else None

    async def get_summary_with_tags(self, branch_id: int) -> SummaryWithTagsDTO:
        """요약과 태그 함께 조회"""
        summary = await self.summary_repo.get_by_branch_id(branch_id)
        tags = await self.branch_tag_repo.get_by_branch(branch_id)

        return SummaryWithTagsDTO(
            summary=summary.model_dump() if summary else None,
            tags=[t.model_dump() for t in tags],
        )

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

    async def get_rating_stats(self) -> RatingStatsDTO:
        """평점 분포 통계"""
        ratings = await self.summary_repo.get_all_ratings()

        if not ratings:
            return RatingStatsDTO(
                min=0,
                max=0,
                avg=0,
                total=0,
                distribution=RatingDistributionDTO(),
            )

        distribution = RatingDistributionDTO()

        for r in ratings:
            if r >= 4.5:
                distribution.range_4_5_to_5_0 += 1
            elif r >= 4.0:
                distribution.range_4_0_to_4_5 += 1
            elif r >= 3.5:
                distribution.range_3_5_to_4_0 += 1
            elif r >= 3.0:
                distribution.range_3_0_to_3_5 += 1
            else:
                distribution.range_below_3_0 += 1

        return RatingStatsDTO(
            min=min(ratings),
            max=max(ratings),
            avg=round(sum(ratings) / len(ratings), 2),
            total=len(ratings),
            distribution=distribution,
        )

    async def regenerate_summary(
        self, branch_id: int, period: str = "all", mode: str = "marketing"
    ) -> str:
        """
        AI 요약 재생성 (generate_summary_with_data 사용)

        Args:
            branch_id: 지점 ID
            period: 기간 (all, 1y, 6m, 3m, 1m) - 힌트용, 실제는 자동 결정
            mode: "marketing" | "operational"

        Returns:
            str: 생성된 요약 텍스트
        """
        result = await self.generate_summary_with_data(branch_id, mode=mode)
        return result.get("summary", "")

    async def generate_summary_with_data(
        self,
        branch_id: int,
        save_to_db: bool = True,
        mode: str = "marketing",
    ) -> dict:
        """
        태그+감정+리뷰 데이터를 활용한 AI 요약 생성

        기간 로직:
        - 1개월 리뷰 >= 30개 → 1개월 요약
        - 1개월 리뷰 < 30개 → 3개월로 확장
        - 3개월 리뷰 < 30개 → 6개월로 확장
        - 6개월 리뷰 < 30개 → 1년으로 확장
        - 1년 리뷰 < 30개 → 실패 (리뷰 부족 메시지)

        Args:
            branch_id: 지점 ID
            save_to_db: DB에 저장할지 여부 (기본 True)
            mode: "marketing" (마케팅 카피) | "operational" (운영 분석)

        Returns:
            dict: {
                "success": bool,
                "summary": str,
                "period": str (3m/6m/1y),
                "period_label": str,
                "start_date": str,
                "end_date": str,
                "review_count": int,
                "mode": str,
                "error": str (실패 시)
            }
        """
        from infrastructure.llm import get_provider
        from infrastructure.llm.prompts import (
            OperationalSummaryPromptBuilder,
            SummaryPromptBuilder,
        )
        from repository.database import get_session_factory

        # 1. 지점 기본 정보 조회
        summary = await self.summary_repo.get_by_branch_id(branch_id)
        if not summary:
            return {
                "success": False,
                "summary": "",
                "error": f"지점 {branch_id}을(를) 찾을 수 없습니다",
            }

        summary_data = summary.model_dump()
        branch_name = summary_data.get("branch_name", f"지점 {branch_id}")

        # 2. 기간별 리뷰 수 확인 및 적절한 기간 선택
        session = get_session_factory()()
        try:
            end_date = utc_now()
            selected_period = None
            review_count = 0
            start_date = None

            for period_config in self.PERIOD_CONFIGS:
                months = period_config["months"]
                start_date = end_date - timedelta(days=months * 30)

                count_result = await session.execute(
                    select(func.count())
                    .select_from(BranchReviewORM)
                    .where(BranchReviewORM.branch_id == branch_id)
                    .where(BranchReviewORM.review_date >= start_date)
                )
                review_count = count_result.scalar_one() or 0

                if review_count >= self.MIN_REVIEWS_FOR_SUMMARY:
                    selected_period = period_config
                    break

            # 3. 어떤 기간도 30개 이상이 아닌 경우 → 전체 기간으로 폴백
            if not selected_period:
                # 전체 리뷰 수 확인
                total_result = await session.execute(
                    select(func.count())
                    .select_from(BranchReviewORM)
                    .where(BranchReviewORM.branch_id == branch_id)
                )
                total_count = total_result.scalar_one() or 0

                if total_count < self.MIN_REVIEWS_FOR_SUMMARY:
                    # 전체 리뷰가 기준(30개) 미만인 경우 생성하지 않음
                    insufficient_msg = SummaryPromptBuilder.get_insufficient_reviews_message(
                        branch_name, total_count
                    )
                    return {
                        "success": False,
                        "summary": insufficient_msg,
                        "period": None,
                        "period_label": None,
                        "review_count": total_count,
                        "mode": mode,
                        "error": "리뷰가 부족합니다",
                    }

                # 리뷰가 있으면 전체 기간으로 진행
                selected_period = {"key": "all", "field": "summary_all", "months": None, "label": "전체 기간"}
                review_count = total_count
                start_date = None  # 전체 기간이므로 시작일 없음

            # 6. 감정별 리뷰 샘플링 (다양성 확보)
            representative_reviews = await self._fetch_representative_reviews(
                session, branch_id, start_date, mode
            )
        finally:
            await session.close()

        period_key = selected_period["key"]
        period_field = selected_period["field"]
        period_label = selected_period["label"]

        # 4. 태그 조회 — BranchTagRepository 활용 (카테고리 조인 포함)
        grouped_tag_sentiments = await self._fetch_grouped_tags(
            branch_id, period_key
        )

        # 5. 감정 통계 조회 (monthly_sentiment_stats 집계)
        sentiment_stats = {"positive": 0, "negative": 0, "neutral": 0, "total": 0}
        if self.sentiment_repo:
            try:
                stats = await self.sentiment_repo.get_stats(branch_id)
                sentiment_stats = {
                    "positive": stats.positive,
                    "negative": stats.negative,
                    "neutral": stats.neutral,
                    "total": stats.total,
                }
            except Exception as e:
                logger.warning(f"감정 통계 조회 실패 (branch_id={branch_id}): {e}")
                try:
                    await self.sentiment_repo._session.rollback()
                except Exception:
                    pass

        # 7. 프롬프트 생성 (모드별 분기)
        if mode == "operational":
            system_prompt, user_prompt = OperationalSummaryPromptBuilder.create_prompt(
                tag_sentiments=grouped_tag_sentiments,
                review_count=review_count,
                representative_reviews=representative_reviews,
                branch_name=branch_name,
                period_label=period_label,
                sentiment_stats=sentiment_stats,
            )
        else:
            system_prompt, user_prompt = (
                SummaryPromptBuilder.create_enhanced_summary_prompt(
                    tag_sentiments=grouped_tag_sentiments,
                    review_count=review_count,
                    representative_reviews=representative_reviews,
                    branch_name=branch_name,
                    period_label=period_label,
                    sentiment_stats=sentiment_stats,
                )
            )

        # 8. LLM 호출 (모드별 파라미터)
        llm_params = {
            "marketing": {"max_tokens": 400, "temperature": 0.7},
            "operational": {"max_tokens": 500, "temperature": 0.5},
        }
        params = llm_params.get(mode, llm_params["marketing"])

        try:
            llm_provider = get_provider()
            response = await llm_provider.async_generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                **params,
            )
            generated_summary = (
                response.content if hasattr(response, "content") else str(response)
            )
        except Exception as e:
            logger.error(f"LLM 호출 실패 (branch_id={branch_id}): {e}")
            return {
                "success": False,
                "summary": "",
                "period": period_key,
                "mode": mode,
                "error": f"AI 요약 생성 실패: {e}",
            }

        # 9. 검증 및 마크다운 정리
        from infrastructure.llm.validator import (
            strip_markdown_formatting,
            validate_summary,
        )

        generated_summary = strip_markdown_formatting(generated_summary)
        validation_mode = "operational" if mode == "operational" else "summary"
        is_valid, errors = validate_summary(generated_summary, mode=validation_mode)
        if not is_valid:
            logger.warning(
                f"검증 실패 (branch_id={branch_id}, mode={mode}): {errors}"
            )

        # 10. DB 저장 (자동 게시) — 선택된 기간만 남기고 나머지 클리어
        if save_to_db:
            try:
                all_period_fields = ["summary_all", "summary_1y", "summary_6m", "summary_3m", "summary_1m"]
                save_data = {"branch_id": branch_id, period_field: generated_summary}
                for f in all_period_fields:
                    if f != period_field:
                        save_data[f] = None
                await self.summary_repo.upsert_by_branch_id(save_data)
                logger.info(
                    f"요약 저장 완료: branch_id={branch_id}, period={period_key}, mode={mode}"
                )
            except Exception as e:
                logger.error(f"요약 저장 실패 (branch_id={branch_id}): {e}")

        return {
            "success": True,
            "summary": generated_summary,
            "period": period_key,
            "period_label": period_label,
            "start_date": start_date.strftime("%Y-%m-%d") if start_date else None,
            "end_date": end_date.strftime("%Y-%m-%d"),
            "review_count": review_count,
            "mode": mode,
        }

    async def _fetch_grouped_tags(
        self, branch_id: int, period_key: str
    ) -> list[dict]:
        """
        monthly_tag_stats에서 기간별 태그를 조회하고 카테고리별로 그룹핑

        월별 태그 통계를 기간(period_key)에 맞게 집계하고,
        결과가 3개 미만이면 branch_tags "all"로 fallback합니다.

        Returns:
            [{"category": "직원친절", "tags": [{"name": "친절", "positive_ratio": 85, ...}]}]
        """
        try:
            # monthly_tag_stats에서 기간별 집계 시도
            if period_key != "all":
                grouped = await self._fetch_tags_from_monthly(branch_id, period_key)
                if len(grouped) >= 1:
                    return grouped

            # fallback: branch_tags "all"
            branch_tags = await self.branch_tag_repo.get_by_branch(
                branch_id, period_type="all", limit=15
            )
            return self._group_tags_by_category(branch_tags)
        except Exception as e:
            logger.warning(f"태그 조회 실패 (branch_id={branch_id}): {e}")
            try:
                await self.branch_tag_repo._session.rollback()
            except Exception:
                pass
            return []

    async def _fetch_tags_from_monthly(
        self, branch_id: int, period_key: str
    ) -> list[dict]:
        """monthly_tag_stats에서 기간 집계 → 카테고리 그룹핑"""
        from repository.database import get_session_factory

        months_map = {"1m": 1, "3m": 3, "6m": 6, "1y": 12}
        months = months_map.get(period_key, 6)
        now = utc_now()
        start_period = (now - timedelta(days=months * 30)).strftime("%Y-%m")

        session = get_session_factory()()
        try:
            stmt = (
                select(
                    MonthlyTagStatsORM.tag_id,
                    MonthlyTagStatsORM.positive_count,
                    MonthlyTagStatsORM.negative_count,
                    MonthlyTagStatsORM.neutral_count,
                )
                .where(MonthlyTagStatsORM.branch_id == branch_id)
                .where(MonthlyTagStatsORM.period >= start_period)
            )
            result = await session.execute(stmt)
            rows = result.all()

            if not rows:
                return []

            # tag_id별 집계
            tag_agg: dict[int, dict[str, int]] = {}
            for row in rows:
                tid = row.tag_id
                if tid not in tag_agg:
                    tag_agg[tid] = {"positive": 0, "negative": 0, "neutral": 0}
                tag_agg[tid]["positive"] += row.positive_count or 0
                tag_agg[tid]["negative"] += row.negative_count or 0
                tag_agg[tid]["neutral"] += row.neutral_count or 0

            if len(tag_agg) < 3:
                return []

            # tag 정보 조회 (name, category)
            tag_ids = list(tag_agg.keys())
            tags_stmt = (
                select(TagORM)
                .options(selectinload(TagORM.category))
                .where(TagORM.id.in_(tag_ids))
            )
            tags_result = await session.execute(tags_stmt)
            tag_rows = tags_result.scalars().all()

            tag_info: dict[int, tuple[str, str]] = {}
            for t in tag_rows:
                from domain.analysis.patterns import normalize_category_name
                cat_name = normalize_category_name(t.category.name) if t.category else "기타"
                tag_info[t.id] = (t.name, cat_name)
        finally:
            await session.close()

        # 카테고리별 그룹핑
        from collections import defaultdict
        category_groups: dict[str, list[dict]] = defaultdict(list)

        # total 기준 상위 15개
        sorted_tags = sorted(
            tag_agg.items(),
            key=lambda x: sum(x[1].values()),
            reverse=True,
        )[:15]

        for tid, counts in sorted_tags:
            name, cat_name = tag_info.get(tid, ("", "기타"))
            if not name:
                continue
            total = counts["positive"] + counts["negative"] + counts["neutral"]
            pos_ratio = round(counts["positive"] / total * 100) if total > 0 else 0
            neg_ratio = round(counts["negative"] / total * 100) if total > 0 else 0
            category_groups[cat_name].append({
                "name": name,
                "positive_ratio": pos_ratio,
                "negative_ratio": neg_ratio,
                "total": total,
            })

        return [
            {"category": cat, "tags": tags}
            for cat, tags in category_groups.items()
        ]

    @staticmethod
    def _group_tags_by_category(branch_tags: list) -> list[dict]:
        """BranchTag 리스트를 카테고리별로 그룹핑"""
        from collections import defaultdict

        category_groups: dict[str, list[dict]] = defaultdict(list)

        for bt in branch_tags:
            tag_info = bt.tags
            if not tag_info:
                continue

            from domain.analysis.patterns import normalize_category_name
            category_name = "기타"
            if tag_info.categories and tag_info.categories.name:
                category_name = normalize_category_name(tag_info.categories.name)

            total = bt.count or 0
            positive = bt.positive_count or 0
            negative = bt.negative_count or 0

            pos_ratio = round(positive / total * 100) if total > 0 else 0
            neg_ratio = round(negative / total * 100) if total > 0 else 0

            category_groups[category_name].append({
                "name": tag_info.name,
                "positive_ratio": pos_ratio,
                "negative_ratio": neg_ratio,
                "total": total,
            })

        return [
            {"category": cat, "tags": tags}
            for cat, tags in category_groups.items()
        ]

    async def _fetch_representative_reviews(
        self,
        session: AsyncSession,
        branch_id: int,
        start_date,
        mode: str,
    ) -> dict[str, list[str]]:
        """
        감정별로 분리된 대표 리뷰 샘플링 (등간격)

        marketing: 긍정 5 + 부정 2 = 7개
        operational: 긍정 4 + 부정 4 = 8개

        Athena에서 최신 리뷰 조회 → Supabase sentiment 병합 → 감정별 분리
        """
        if mode == "operational":
            pos_limit, neg_limit = 4, 4
        else:
            pos_limit, neg_limit = 5, 2

        result = {"positive": [], "negative": []}

        if self.athena_client is not None:
            try:
                return await self._fetch_representative_reviews_via_athena(
                    branch_id, start_date, pos_limit, neg_limit
                )
            except Exception as e:
                logger.warning(f"Athena 리뷰 샘플링 실패, Supabase 폴백: {e}")

        # Supabase 폴백 → SQLAlchemy
        try:
            pos_stmt = (
                select(BranchReviewORM.content)
                .where(BranchReviewORM.branch_id == branch_id)
                .where(BranchReviewORM.sentiment == "positive")
            )
            if start_date is not None:
                pos_stmt = pos_stmt.where(
                    BranchReviewORM.review_date >= start_date
                )
            pos_stmt = (
                pos_stmt
                .order_by(BranchReviewORM.review_date.desc())
                .limit(30)
            )
            pos_result = await session.execute(pos_stmt)
            pos_reviews = [
                row.content[:250] for row in pos_result.all() if row.content
            ]
            result["positive"] = self._sample_evenly(pos_reviews, pos_limit)

            neg_stmt = (
                select(BranchReviewORM.content)
                .where(BranchReviewORM.branch_id == branch_id)
                .where(BranchReviewORM.sentiment == "negative")
            )
            if start_date is not None:
                neg_stmt = neg_stmt.where(
                    BranchReviewORM.review_date >= start_date
                )
            neg_stmt = (
                neg_stmt
                .order_by(BranchReviewORM.review_date.desc())
                .limit(30)
            )
            neg_result = await session.execute(neg_stmt)
            neg_reviews = [
                row.content[:250] for row in neg_result.all() if row.content
            ]
            result["negative"] = self._sample_evenly(neg_reviews, neg_limit)

        except Exception as e:
            logger.warning(f"리뷰 샘플링 실패 (branch_id={branch_id}): {e}")

        return result

    async def _fetch_representative_reviews_via_athena(
        self,
        branch_id: int,
        start_date,
        pos_limit: int,
        neg_limit: int,
    ) -> dict[str, list[str]]:
        """Athena 리뷰 + Supabase sentiment → 감정별 분리 샘플링"""
        date_from = start_date.strftime("%Y-%m-%d") if start_date else None

        rows, _ = await asyncio.to_thread(
            self.athena_client.fetch_reviews_by_branch,
            branch_id=branch_id,
            date_from=date_from,
            limit=50,
        )

        if not rows:
            return {"positive": [], "negative": []}

        # Supabase에서 sentiment 병합
        review_ids = [int(r["review_id"]) for r in rows if r.get("review_id")]
        sentiment_map = {}
        if review_ids:
            sentiment_map = await self.review_repo.get_sentiments_by_review_ids(review_ids)

        pos_reviews = []
        neg_reviews = []
        for row in rows:
            content = row.get("content", "")
            if not content or not content.strip():
                continue
            rid = int(row["review_id"]) if row.get("review_id") else None
            sent = sentiment_map.get(rid, "neutral") if rid else "neutral"
            if sent == "positive":
                pos_reviews.append(content[:250])
            elif sent == "negative":
                neg_reviews.append(content[:250])

        return {
            "positive": self._sample_evenly(pos_reviews, pos_limit),
            "negative": self._sample_evenly(neg_reviews, neg_limit),
        }

    @staticmethod
    def _sample_evenly(items: list, n: int) -> list:
        """리스트에서 등간격으로 n개 샘플링"""
        if not items or n <= 0:
            return []
        if len(items) <= n:
            return items
        step = len(items) / n
        return [items[int(i * step)] for i in range(n)]

    async def generate_pending_summary(
        self,
        branch_id: int,
        period: str = "1m",
    ) -> dict:
        """
        AI 요약을 생성하여 pending_summaries에 저장 (승인 대기 상태)

        스케줄러에서 자동으로 호출되며, 운영자 승인 후 실제 요약으로 적용됩니다.

        Args:
            branch_id: 지점 ID
            period: 기간 키 (1m, 3m, 6m, 1y, all)

        Returns:
            dict: {
                "success": bool,
                "summary": str,
                "period": str,
                "error": str (실패 시)
            }
        """
        # 기존 generate_summary_with_data 로직 재사용 (save_to_db=False)
        result = await self.generate_summary_with_data(branch_id, save_to_db=False)

        if not result.get("success"):
            return result

        generated_summary = result.get("summary", "")
        generated_period = result.get("period", period)

        # pending_summaries에 저장
        try:
            # 현재 pending_summaries 조회
            summary = await self.summary_repo.get_by_branch_id(branch_id)
            if not summary:
                return {
                    "success": False,
                    "summary": "",
                    "period": generated_period,
                    "error": f"지점 {branch_id}을(를) 찾을 수 없습니다",
                }

            current_pending = summary.pending_summaries or {}

            # 새 pending 요약 추가
            current_pending[generated_period] = generated_summary

            # DB 업데이트
            await self.summary_repo.set_pending_summary(branch_id, current_pending)

            logger.info(
                f"Pending 요약 생성 완료: branch_id={branch_id}, period={generated_period}"
            )

            return {
                "success": True,
                "summary": generated_summary,
                "period": generated_period,
                "period_label": result.get("period_label"),
                "review_count": result.get("review_count"),
            }
        except Exception as e:
            logger.error(f"Pending 요약 저장 실패 (branch_id={branch_id}): {e}")
            return {
                "success": False,
                "summary": generated_summary,
                "period": generated_period,
                "error": f"Pending 저장 실패: {e}",
            }

    async def apply_pending_summary(
        self, branch_id: int, period: str
    ) -> PendingSummaryResultDTO:
        """대기 중인 요약을 적용 (pending → main)"""
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

    async def get_branch_detail(
        self, branch_id: int, include_summaries: bool = True, max_reviews: int = 500
    ) -> BranchDetailDTO | None:
        """지점 상세 분석 (JSON 반환)"""
        from domain.analysis import KeywordExtractor, RuleBasedABSA

        # 1. 기본 정보 조회
        summary = await self.summary_repo.get_by_branch_id(branch_id)
        if not summary:
            return None

        summary_data = summary.model_dump()
        branch_name = summary_data.get("branch_name", f"지점 {branch_id}")
        location = summary_data.get("region", "")

        reviews_result = await self.review_repo.get_by_branch(
            branch_id=branch_id, limit=max_reviews
        )
        reviews_data = reviews_result.reviews
        review_count = reviews_result.total

        if not reviews_data:
            return BranchDetailDTO(
                branch_id=branch_id,
                branch_name=branch_name,
                location=location,
                review_count=0,
                tags=[],
                summaries=SummariesOutputDTO(),
                reviews=[],
            )

        review_texts = [r.get("content", "") or "" for r in reviews_data]

        def extract_keywords():
            extractor = KeywordExtractor()
            return extractor.extract_batch(review_texts)

        all_keywords = await asyncio.to_thread(extract_keywords)

        def classify_reviews():
            classifier = RuleBasedABSA()
            results = []
            tag_totals = {}

            for keywords, review_text in zip(all_keywords, review_texts, strict=False):
                result = classifier.classify_review(review_text, keywords[:10])

                tag_parts = []
                for tag, sentiments in result.items():
                    pos = len(sentiments.get("positive", []))
                    neg = len(sentiments.get("negative", []))
                    neu = len(sentiments.get("neutral", []))

                    if tag not in tag_totals:
                        tag_totals[tag] = {
                            "positive": 0,
                            "negative": 0,
                            "neutral": 0,
                            "total": 0,
                        }
                    tag_totals[tag]["positive"] += pos
                    tag_totals[tag]["negative"] += neg
                    tag_totals[tag]["neutral"] += neu
                    tag_totals[tag]["total"] += pos + neg + neu

                    if pos > neg:
                        tag_parts.append(f"{tag}(+)")
                    elif neg > pos:
                        tag_parts.append(f"{tag}(-)")

                results.append(", ".join(tag_parts))

            return results, tag_totals

        tag_sentiments, tag_totals = await asyncio.to_thread(classify_reviews)

        sorted_tags = sorted(
            tag_totals.items(), key=lambda x: x[1]["total"], reverse=True
        )
        tags_list = [
            TagSentimentCountDTO(
                name=tag,
                total=counts["total"],
                positive=counts["positive"],
                negative=counts["negative"],
                neutral=counts["neutral"],
            )
            for tag, counts in sorted_tags
        ]

        reviews_output = []
        for i, review in enumerate(reviews_data):
            reviews_output.append(
                ReviewOutputDTO(
                    id=review.get("review_id"),
                    date=review.get("review_date"),
                    content=review.get("content", "")[:500],
                    keywords=all_keywords[i][:10] if i < len(all_keywords) else [],
                    tag_sentiments=tag_sentiments[i]
                    if i < len(tag_sentiments)
                    else "",
                )
            )

        summaries_output = SummariesOutputDTO()
        if include_summaries:
            summaries_output = SummariesOutputDTO(
                summary_1m=summary_data.get("summary_1m", "") or "",
                summary_3m=summary_data.get("summary_3m", "") or "",
                summary_6m=summary_data.get("summary_6m", "") or "",
                summary_1y=summary_data.get("summary_1y", "") or "",
                summary_all=summary_data.get("summary_all", "") or "",
            )

        return BranchDetailDTO(
            branch_id=branch_id,
            branch_name=branch_name,
            location=location,
            review_count=review_count,
            tags=tags_list,
            summaries=summaries_output,
            reviews=reviews_output,
        )

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
        """지점별 원본 리뷰 목록 조회 (Athena primary, Supabase fallback)

        Athena 원본에는 sentiment/car_model이 없으므로 해당 필터 시 Supabase 사용.
        """
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
                logger.warning(f"Athena 리뷰 조회 실패, Supabase 폴백: {e}")

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

        # Supabase에서 sentiment 병합
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
        """
        지점별 차량 모델 태그 분석

        monthly_car_model_tag_stats + car_models_master + branch_car_models에서 집계.

        Args:
            branch_id: 지점 ID
            car_model: 특정 차량 모델만 조회 (None이면 전체)

        Returns:
            BranchCarModelsDTO: 차량별 태그 통계
        """
        from repository.car_model_repository import CarModelRepository
        from repository.database import get_session_factory

        session = get_session_factory()()
        try:
            repo = CarModelRepository(session)

            try:
                rows = await repo.get_car_model_tags(branch_id, car_model)
            except Exception as e:
                logger.warning(f"차량 태그 조회 실패 (branch_id={branch_id}): {e}")
                return BranchCarModelsDTO(branch_id=branch_id, car_models=[])

            if not rows:
                return BranchCarModelsDTO(branch_id=branch_id, car_models=[])

            # 차량별로 그룹화
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

            # 리뷰 수 조회 (branch_reviews 테이블)
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
        finally:
            await session.close()

        # DTO로 변환
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
