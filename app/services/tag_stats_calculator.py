"""태그 통계 계산기

branch_tags 데이터로부터 카테고리 통계, 현상유지/보완필요, Top 태그를 산출합니다.
모든 계산 메서드는 순수 함수(static)로, 외부 상태에 의존하지 않습니다.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from core.constants import IMPROVEMENT_NEGATIVE_RATIO, STRENGTH_POSITIVE_RATIO
from domain.analysis.patterns import (
    AFFILIATE_CATEGORIES,
    CATEGORY_NEGATIVE_LABELS,
    CATEGORY_POSITIVE_LABELS,
    normalize_category_name,
    resolve_tag_category,
)
from schemas.report import TagRankItem

if TYPE_CHECKING:
    from repository.branch_tag_repository import BranchTagRepository

logger = logging.getLogger(__name__)

MIN_PERIOD_TAG_COUNT = 3


class TagStatsCalculator:
    """태그 감정 통계 계산"""

    def __init__(self, branch_tag_repo: BranchTagRepository) -> None:
        self.branch_tag_repo = branch_tag_repo

    async def compute(
        self,
        branch_id: int,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict:
        """Step 2 오케스트레이터: 태그 조회 → 통계 산출

        review_tag_mappings RPC(getTagStatsByPeriod)를 primary로 사용하고,
        결과가 MIN_PERIOD_TAG_COUNT 미만이면 branch_tags(all) fallback.
        """
        # Primary: RPC로 기간별 통계 조회 (날짜 없으면 넓은 범위 사용)
        rpc_start = start_date or datetime(2020, 1, 1)
        rpc_end = end_date or datetime.now()
        try:
            period_tags = await self.branch_tag_repo.get_tag_stats_by_period(
                branch_id, rpc_start, rpc_end
            )
            if len(period_tags) >= MIN_PERIOD_TAG_COUNT:
                return self._compute_from_rpc_rows(period_tags)
        except Exception as e:
            logger.warning("RPC 태그 조회 실패, fallback: %s", e)

        # Fallback: branch_tags "all" (대시보드 태그 배지용으로 유지됨)
        try:
            all_tags = await self.branch_tag_repo.get_by_branch(
                branch_id, period_type="all", limit=100
            )
        except Exception as e:
            logger.warning("태그 조회 실패 (branch_id=%s): %s", branch_id, e)
            return {}

        if not all_tags:
            return {}

        tag_sentiments, sentiment_stats, category_stats, tag_details = (
            self.compute_category_stats(all_tags)
        )
        if not tag_sentiments:
            return {}

        strengths, improvements, strengths_detail, improvements_detail = (
            self.compute_strengths_improvements(category_stats)
        )

        top_positive, top_negative, top_tags_detail = (
            self.compute_top_tags(tag_details)
        )

        return {
            "tag_sentiments": tag_sentiments,
            "sentiment_stats": sentiment_stats,
            "strengths": strengths,
            "improvements": improvements,
            "strengths_detail": strengths_detail,
            "improvements_detail": improvements_detail,
            "tag_details": tag_details,
            "top_positive_tags": top_positive,
            "top_negative_tags": top_negative,
            "top_tags_detail": top_tags_detail,
            "tag_by_category": category_stats,
        }

    @staticmethod
    def _rpc_val(row: dict, *keys, default=None):
        """RPC 행에서 값 조회 (camelCase/snake_case 모두 지원)"""
        for key in keys:
            val = row.get(key)
            if val is not None:
                return val
        return default

    def _compute_from_rpc_rows(self, rows: list[dict]) -> dict:
        """RPC 결과 행 → 기존 compute() 반환 포맷 변환"""
        tag_sentiments: list[dict] = []
        category_stats: dict[str, dict] = {}
        tag_details: list[dict] = []
        total_pos = 0
        total_neg = 0
        total_neu = 0

        for row in rows:
            name = self._rpc_val(row, "tagName", "tag_name", default="")
            if not name:
                continue
            pos = self._rpc_val(row, "positiveCount", "positive_count", default=0) or 0
            neg = self._rpc_val(row, "negativeCount", "negative_count", default=0) or 0
            neu = self._rpc_val(row, "neutralCount", "neutral_count", default=0) or 0
            total = self._rpc_val(row, "totalCount", "total_count", default=0) or 0

            tag_sentiments.append({
                "name": name, "positive": pos, "negative": neg,
                "neutral": neu, "total": total,
            })
            total_pos += pos
            total_neg += neg
            total_neu += neu

            db_cat = self._rpc_val(row, "categoryName", "category_name", default="") or ""
            cat_name = resolve_tag_category(name, db_cat)
            tag_details.append({
                "tag_name": name, "category_name": cat_name,
                "positive": pos, "negative": neg, "total": total,
            })
            if cat_name and total > 0:
                if cat_name not in category_stats:
                    category_stats[cat_name] = {"positive": 0, "negative": 0, "total": 0}
                category_stats[cat_name]["positive"] += pos
                category_stats[cat_name]["negative"] += neg
                category_stats[cat_name]["total"] += total

        if not tag_sentiments:
            return {}

        sentiment_stats = {
            "positive": total_pos, "negative": total_neg,
            "neutral": total_neu, "total": total_pos + total_neg + total_neu,
        }

        strengths, improvements, strengths_detail, improvements_detail = (
            self.compute_strengths_improvements(category_stats)
        )
        top_positive, top_negative, top_tags_detail = (
            self.compute_top_tags(tag_details)
        )

        return {
            "tag_sentiments": tag_sentiments,
            "sentiment_stats": sentiment_stats,
            "strengths": strengths,
            "improvements": improvements,
            "strengths_detail": strengths_detail,
            "improvements_detail": improvements_detail,
            "tag_details": tag_details,
            "top_positive_tags": top_positive,
            "top_negative_tags": top_negative,
            "top_tags_detail": top_tags_detail,
            "tag_by_category": category_stats,
        }

    @staticmethod
    def compute_category_stats(
        all_tags: list,
    ) -> tuple[list[dict], dict, dict[str, dict], list[dict]]:
        """태그 → 감정통계 + 카테고리통계 + 태그상세 변환"""
        tag_sentiments: list[dict] = []
        total_pos = 0
        total_neg = 0
        category_stats: dict[str, dict] = {}
        tag_details: list[dict] = []

        for bt in all_tags:
            try:
                tag_info = bt.model_dump().get("tags") or {}
            except Exception:
                tag_info = {}
            name = tag_info.get("name", "")
            if not name:
                continue

            pos = bt.positive_count or 0
            neg = bt.negative_count or 0
            neu = bt.neutral_count or 0
            total = pos + neg + neu

            tag_sentiments.append({
                "name": name,
                "positive": pos,
                "negative": neg,
                "neutral": neu,
                "total": total,
            })
            total_pos += pos
            total_neg += neg

            cat_info = tag_info.get("categories") or {}
            db_cat = cat_info.get("name", "")
            cat_name = resolve_tag_category(name, db_cat)

            tag_details.append({
                "tag_name": name,
                "category_name": cat_name,
                "positive": pos,
                "negative": neg,
                "total": total,
            })

            if cat_name and total > 0:
                if cat_name not in category_stats:
                    category_stats[cat_name] = {"positive": 0, "negative": 0, "total": 0}
                category_stats[cat_name]["positive"] += pos
                category_stats[cat_name]["negative"] += neg
                category_stats[cat_name]["total"] += total

        total_neu = sum(
            ts.get("neutral", 0) for ts in tag_sentiments
        )
        total_all = total_pos + total_neg + total_neu
        sentiment_stats = {
            "positive": total_pos,
            "negative": total_neg,
            "neutral": total_neu,
            "total": total_all,
        }

        return tag_sentiments, sentiment_stats, category_stats, tag_details

    @staticmethod
    def compute_strengths_improvements(
        category_stats: dict[str, dict],
    ) -> tuple[list[str], list[str], list[dict], list[dict]]:
        """현상유지/보완필요 산출 (기존 list[str] + 신규 detail)"""
        strengths: list[str] = []
        strengths_detail: list[dict] = []
        sorted_positive = sorted(
            category_stats.items(),
            key=lambda x: x[1]["positive"] / x[1]["total"] if x[1]["total"] > 0 else 0,
            reverse=True,
        )
        for cat_name, stats in sorted_positive:
            if stats["total"] == 0:
                continue
            pos_ratio = round(stats["positive"] / stats["total"] * 100)
            if pos_ratio >= STRENGTH_POSITIVE_RATIO:
                label = CATEGORY_POSITIVE_LABELS.get(cat_name, cat_name)
                strengths.append(f"{label}({pos_ratio}%)")
                strengths_detail.append({"category_name": cat_name, "ratio": pos_ratio})
            if len(strengths) >= 3:
                break

        improvements: list[str] = []
        improvements_detail: list[dict] = []
        sorted_negative = sorted(
            category_stats.items(),
            key=lambda x: x[1]["negative"] / x[1]["total"] if x[1]["total"] > 0 else 0,
            reverse=True,
        )
        for cat_name, stats in sorted_negative:
            if stats["total"] == 0:
                continue
            neg_ratio = round(stats["negative"] / stats["total"] * 100)
            if neg_ratio >= IMPROVEMENT_NEGATIVE_RATIO:
                label = CATEGORY_NEGATIVE_LABELS.get(cat_name, cat_name)
                improvements.append(f"{label}({neg_ratio}%)")
                improvements_detail.append({"category_name": cat_name, "ratio": neg_ratio})
            if len(improvements) >= 3:
                break

        return strengths, improvements, strengths_detail, improvements_detail

    @staticmethod
    def compute_trend(
        current_category_stats: dict[str, dict],
        previous_category_stats: dict[str, dict],
        current_sentiment: dict,
        previous_sentiment: dict,
    ) -> dict:
        """현재 기간 vs 이전 기간 카테고리별 트렌드 산출

        Returns:
            dict: {
                overall_positive_change: int (pp),
                overall_negative_change: int (pp),
                category_trends: list[dict],
            }
        """
        # 전체 긍정/부정률 변화
        cur_total = current_sentiment.get("total", 0)
        prev_total = previous_sentiment.get("total", 0)

        cur_pos_pct = round(current_sentiment.get("positive", 0) / cur_total * 100) if cur_total > 0 else 0
        prev_pos_pct = round(previous_sentiment.get("positive", 0) / prev_total * 100) if prev_total > 0 else 0
        cur_neg_pct = round(current_sentiment.get("negative", 0) / cur_total * 100) if cur_total > 0 else 0
        prev_neg_pct = round(previous_sentiment.get("negative", 0) / prev_total * 100) if prev_total > 0 else 0

        # 카테고리별 트렌드
        all_categories = set(current_category_stats.keys()) | set(previous_category_stats.keys())
        category_trends = []
        for cat_name in sorted(all_categories):
            cur = current_category_stats.get(cat_name, {"positive": 0, "total": 0})
            prev = previous_category_stats.get(cat_name, {"positive": 0, "total": 0})

            cur_ratio = round(cur["positive"] / cur["total"] * 100) if cur.get("total", 0) > 0 else 0
            prev_ratio = round(prev["positive"] / prev["total"] * 100) if prev.get("total", 0) > 0 else 0
            change = cur_ratio - prev_ratio

            if change >= 3:
                direction = "up"
            elif change <= -3:
                direction = "down"
            else:
                direction = "stable"

            category_trends.append({
                "category_name": cat_name,
                "current_ratio": cur_ratio,
                "previous_ratio": prev_ratio,
                "change": change,
                "direction": direction,
            })

        # 변화 크기 순 정렬 (절대값 내림차순)
        category_trends.sort(key=lambda t: abs(t["change"]), reverse=True)

        return {
            "overall_positive_change": cur_pos_pct - prev_pos_pct,
            "overall_negative_change": cur_neg_pct - prev_neg_pct,
            "category_trends": category_trends,
        }

    @staticmethod
    def compute_top_tags(
        tag_details: list[dict],
    ) -> tuple[list[TagRankItem], list[TagRankItem], list[dict]]:
        """Top 5 긍정/부정 태그 + TopTagItem detail 산출

        동일 category_name의 태그를 합산하여 카테고리 단위로 순위를 산출합니다.
        """
        affiliate_tags = [
            t for t in tag_details
            if t["category_name"] in AFFILIATE_CATEGORIES and t["total"] > 0
        ]

        # 카테고리별 집계
        cat_agg: dict[str, dict] = {}
        for t in affiliate_tags:
            cat = t["category_name"]
            if cat not in cat_agg:
                cat_agg[cat] = {"positive": 0, "negative": 0, "total": 0}
            cat_agg[cat]["positive"] += t["positive"]
            cat_agg[cat]["negative"] += t["negative"]
            cat_agg[cat]["total"] += t["total"]

        cat_list = [
            {"category_name": cat, **vals}
            for cat, vals in cat_agg.items()
        ]

        top_positive_raw = sorted(cat_list, key=lambda t: t["positive"], reverse=True)[:5]
        top_negative_raw = sorted(cat_list, key=lambda t: t["negative"], reverse=True)[:5]
        top_negative_raw = [t for t in top_negative_raw if t["negative"] > 0]

        top_positive = [
            TagRankItem(
                tag_name=t["category_name"],
                category_name=t["category_name"],
                count=t["positive"],
                ratio=round(t["positive"] / t["total"] * 100) if t["total"] > 0 else 0,
            )
            for t in top_positive_raw
        ]
        top_negative = [
            TagRankItem(
                tag_name=t["category_name"],
                category_name=t["category_name"],
                count=t["negative"],
                ratio=round(t["negative"] / t["total"] * 100) if t["total"] > 0 else 0,
            )
            for t in top_negative_raw
        ]

        # TopTagItem detail (프론트/API 구조화 제공용)
        top_tags_detail = [
            {
                "name": t["category_name"],
                "count": t["positive"],
                "positive_ratio": round(t["positive"] / t["total"] * 100) if t["total"] > 0 else 0,
            }
            for t in top_positive_raw
        ]

        return top_positive, top_negative, top_tags_detail
