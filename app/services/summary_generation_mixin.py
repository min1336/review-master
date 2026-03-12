"""요약 생성 Mixin

SummaryService에서 분리된 AI 요약 생성 관련 메서드.
의존성: summary_repo, branch_tag_repo, review_repo, sentiment_repo, athena_client
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.timezone import utc_now
from repository.orm_models import (
    BranchReviewORM,
    MonthlyTagStatsORM,
    TagORM,
)

logger = logging.getLogger(__name__)


class SummaryGenerationMixin:
    """AI 요약 생성 메서드"""

    # 기간별 설정 (우선순위 순서)
    PERIOD_CONFIGS = [
        {"key": "1m", "field": "summary_1m", "months": 1, "label": "최근 1개월"},
        {"key": "3m", "field": "summary_3m", "months": 3, "label": "최근 3개월"},
        {"key": "6m", "field": "summary_6m", "months": 6, "label": "최근 6개월"},
        {"key": "1y", "field": "summary_1y", "months": 12, "label": "최근 1년"},
    ]
    MIN_REVIEWS_FOR_SUMMARY = 30

    async def generate_summary_with_data(
        self,
        branch_id: int,
        save_to_db: bool = True,
        mode: str = "marketing",
    ) -> dict:
        """태그+감정+리뷰 데이터를 활용한 AI 요약 생성"""
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
        async with get_session_factory()() as session:
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
                total_result = await session.execute(
                    select(func.count())
                    .select_from(BranchReviewORM)
                    .where(BranchReviewORM.branch_id == branch_id)
                )
                total_count = total_result.scalar_one() or 0

                if total_count < self.MIN_REVIEWS_FOR_SUMMARY:
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

                selected_period = {"key": "all", "field": "summary_all", "months": None, "label": "전체 기간"}
                review_count = total_count
                start_date = None

            # 6. 감정별 리뷰 샘플링 (다양성 확보)
            representative_reviews = await self._fetch_representative_reviews(
                session, branch_id, start_date, mode
            )

        period_key = selected_period["key"]
        period_field = selected_period["field"]
        period_label = selected_period["label"]

        # 4. 태그 조회
        grouped_tag_sentiments = await self._fetch_grouped_tags(
            branch_id, period_key
        )

        # 5. 감정 통계 조회
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
                logger.warning("감정 통계 조회 실패 (branch_id=%s): %s", branch_id, e)
                try:
                    await self.sentiment_repo.rollback()
                except Exception:
                    pass

        # 7. 프롬프트 생성
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

        # 8. LLM 호출
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
            logger.error("LLM 호출 실패 (branch_id=%s): %s", branch_id, e)
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

        # 10. DB 저장
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
                logger.error("요약 저장 실패 (branch_id=%s): %s", branch_id, e)

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
        """monthly_tag_stats에서 기간별 태그를 조회하고 카테고리별로 그룹핑"""
        try:
            if period_key != "all":
                grouped = await self._fetch_tags_from_monthly(branch_id, period_key)
                if len(grouped) >= 1:
                    return grouped

            branch_tags = await self.branch_tag_repo.get_by_branch(
                branch_id, period_type="all", limit=15
            )
            return self._group_tags_by_category(branch_tags)
        except Exception as e:
            logger.warning("태그 조회 실패 (branch_id=%s): %s", branch_id, e)
            try:
                await self.branch_tag_repo.rollback()
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

        async with get_session_factory()() as session:
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
                from domain.analysis.patterns import resolve_tag_category
                cat_name = resolve_tag_category(t.name, t.category.name) if t.category else "기타"
                tag_info[t.id] = (t.name, cat_name)

        from collections import defaultdict
        category_groups: dict[str, list[dict]] = defaultdict(list)

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

            from domain.analysis.patterns import resolve_tag_category
            category_name = "기타"
            if tag_info.categories and tag_info.categories.name:
                category_name = resolve_tag_category(tag_info.name, tag_info.categories.name)

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
        """감정별로 분리된 대표 리뷰 샘플링 (등간격)"""
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
                logger.warning("Athena 리뷰 샘플링 실패, Supabase 폴백: %s", e)

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
            logger.warning("리뷰 샘플링 실패 (branch_id=%s): %s", branch_id, e)

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
        """AI 요약을 생성하여 pending_summaries에 저장 (승인 대기 상태)"""
        result = await self.generate_summary_with_data(branch_id, save_to_db=False)

        if not result.get("success"):
            return result

        generated_summary = result.get("summary", "")
        generated_period = result.get("period", period)

        try:
            summary = await self.summary_repo.get_by_branch_id(branch_id)
            if not summary:
                return {
                    "success": False,
                    "summary": "",
                    "period": generated_period,
                    "error": f"지점 {branch_id}을(를) 찾을 수 없습니다",
                }

            current_pending = summary.pending_summaries or {}
            current_pending[generated_period] = generated_summary
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
            logger.error("Pending 요약 저장 실패 (branch_id=%s): %s", branch_id, e)
            return {
                "success": False,
                "summary": generated_summary,
                "period": generated_period,
                "error": f"Pending 저장 실패: {e}",
            }
