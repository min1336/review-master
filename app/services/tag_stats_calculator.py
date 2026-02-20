"""태그 통계 계산기

branch_tags 데이터로부터 카테고리 통계, 현상유지/보완필요, Top 태그를 산출합니다.
모든 계산 메서드는 순수 함수(static)로, 외부 상태에 의존하지 않습니다.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.constants import IMPROVEMENT_NEGATIVE_RATIO, STRENGTH_POSITIVE_RATIO
from domain.analysis.patterns import AFFILIATE_CATEGORIES
from schemas.report import TagRankItem

if TYPE_CHECKING:
    from repository.branch_tag_repository import BranchTagRepository

logger = logging.getLogger(__name__)


class TagStatsCalculator:
    """태그 감정 통계 계산"""

    def __init__(self, branch_tag_repo: BranchTagRepository) -> None:
        self.branch_tag_repo = branch_tag_repo

    async def compute(self, branch_id: int) -> dict:
        """Step 2 오케스트레이터: 태그 조회 → 통계 산출"""
        try:
            all_tags = await self.branch_tag_repo.get_by_branch(
                branch_id, period_type="all", limit=100
            )
        except Exception as e:
            logger.warning(f"태그 조회 실패 (branch_id={branch_id}): {e}")
            return {}

        if not all_tags:
            return {}

        # Step 2-1: 태그→감정통계+카테고리통계+태그상세
        tag_sentiments, sentiment_stats, category_stats, tag_details = (
            self.compute_category_stats(all_tags)
        )
        if not tag_sentiments:
            return {}

        # Step 2-2: 현상유지/보완필요
        strengths, improvements, strengths_detail, improvements_detail = (
            self.compute_strengths_improvements(category_stats)
        )

        # Step 2-3: Top 5 긍정/부정 태그
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
            cat_name = cat_info.get("name", "")

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
                strengths.append(f"{cat_name}({pos_ratio}%)")
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
                improvements.append(f"{cat_name}({neg_ratio}%)")
                improvements_detail.append({"category_name": cat_name, "ratio": neg_ratio})
            if len(improvements) >= 3:
                break

        return strengths, improvements, strengths_detail, improvements_detail

    @staticmethod
    def compute_top_tags(
        tag_details: list[dict],
    ) -> tuple[list[TagRankItem], list[TagRankItem], list[dict]]:
        """Top 5 긍정/부정 태그 + TopTagItem detail 산출"""
        affiliate_tags = [
            t for t in tag_details
            if t["category_name"] in AFFILIATE_CATEGORIES and t["total"] > 0
        ]

        top_positive_raw = sorted(affiliate_tags, key=lambda t: t["positive"], reverse=True)[:5]
        top_negative_raw = sorted(affiliate_tags, key=lambda t: t["negative"], reverse=True)[:5]
        top_negative_raw = [t for t in top_negative_raw if t["negative"] > 0]

        top_positive = [
            TagRankItem(
                tag_name=t["tag_name"],
                category_name=t["category_name"],
                count=t["positive"],
                ratio=round(t["positive"] / t["total"] * 100) if t["total"] > 0 else 0,
            )
            for t in top_positive_raw
        ]
        top_negative = [
            TagRankItem(
                tag_name=t["tag_name"],
                category_name=t["category_name"],
                count=t["negative"],
                ratio=round(t["negative"] / t["total"] * 100) if t["total"] > 0 else 0,
            )
            for t in top_negative_raw
        ]

        # TopTagItem detail (프론트/API 구조화 제공용)
        top_tags_detail = [
            {
                "name": t["tag_name"],
                "count": t["positive"],
                "positive_ratio": round(t["positive"] / t["total"] * 100) if t["total"] > 0 else 0,
            }
            for t in top_positive_raw
        ]

        return top_positive, top_negative, top_tags_detail
