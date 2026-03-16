"""TagStatsCalculator 정적 메서드 단위 테스트

compute_strengths_improvements, compute_trend, compute_top_tags, _rpc_val
DB 의존 없이 순수 함수만 테스트
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock

from services.tag_stats_calculator import TagStatsCalculator
from core.constants import STRENGTH_POSITIVE_RATIO, IMPROVEMENT_NEGATIVE_RATIO


# ── _rpc_val ──────────────────────────────────────────


class TestRpcVal:
    def test_camel_case_key(self):
        row = {"tagName": "친절"}
        assert TagStatsCalculator._rpc_val(row, "tagName", "tag_name") == "친절"

    def test_snake_case_key(self):
        row = {"tag_name": "친절"}
        assert TagStatsCalculator._rpc_val(row, "tagName", "tag_name") == "친절"

    def test_first_key_priority(self):
        row = {"tagName": "camel", "tag_name": "snake"}
        assert TagStatsCalculator._rpc_val(row, "tagName", "tag_name") == "camel"

    def test_missing_key_returns_default(self):
        row = {}
        assert TagStatsCalculator._rpc_val(row, "tagName", default="기본") == "기본"

    def test_none_value_skipped(self):
        row = {"tagName": None, "tag_name": "있음"}
        assert TagStatsCalculator._rpc_val(row, "tagName", "tag_name") == "있음"


# ── compute_strengths_improvements ────────────────────


class TestComputeStrengthsImprovements:
    def test_high_positive_is_strength(self):
        stats = {
            "직원친절": {"positive": 80, "negative": 10, "total": 100},
        }
        strengths, improvements, s_detail, i_detail = (
            TagStatsCalculator.compute_strengths_improvements(stats)
        )
        assert len(strengths) == 1
        assert "직원" in strengths[0] or "친절" in strengths[0]
        assert s_detail[0]["ratio"] == 80

    def test_high_negative_is_improvement(self):
        stats = {
            "청결": {"positive": 30, "negative": 50, "total": 100},
        }
        strengths, improvements, s_detail, i_detail = (
            TagStatsCalculator.compute_strengths_improvements(stats)
        )
        assert len(improvements) == 1
        assert i_detail[0]["ratio"] == 50

    def test_max_three_strengths(self):
        stats = {
            f"cat{i}": {"positive": 90, "negative": 5, "total": 100}
            for i in range(5)
        }
        strengths, _, _, _ = TagStatsCalculator.compute_strengths_improvements(stats)
        assert len(strengths) <= 3

    def test_max_three_improvements(self):
        stats = {
            f"cat{i}": {"positive": 10, "negative": 80, "total": 100}
            for i in range(5)
        }
        _, improvements, _, _ = TagStatsCalculator.compute_strengths_improvements(stats)
        assert len(improvements) <= 3

    def test_zero_total_excluded(self):
        stats = {
            "직원친절": {"positive": 0, "negative": 0, "total": 0},
        }
        strengths, improvements, s_detail, i_detail = (
            TagStatsCalculator.compute_strengths_improvements(stats)
        )
        assert len(strengths) == 0
        assert len(improvements) == 0

    def test_boundary_strength_ratio(self):
        """STRENGTH_POSITIVE_RATIO(60%) 경계값"""
        stats = {
            "직원친절": {"positive": 60, "negative": 20, "total": 100},
        }
        strengths, _, _, _ = TagStatsCalculator.compute_strengths_improvements(stats)
        assert len(strengths) == 1  # 60% >= 60% → 포함

    def test_below_strength_ratio_excluded(self):
        stats = {
            "직원친절": {"positive": 59, "negative": 21, "total": 100},
        }
        strengths, _, _, _ = TagStatsCalculator.compute_strengths_improvements(stats)
        assert len(strengths) == 0  # 59% < 60% → 제외

    def test_boundary_improvement_ratio(self):
        """IMPROVEMENT_NEGATIVE_RATIO(20%) 경계값"""
        stats = {
            "청결": {"positive": 50, "negative": 20, "total": 100},
        }
        _, improvements, _, _ = TagStatsCalculator.compute_strengths_improvements(stats)
        assert len(improvements) == 1  # 20% >= 20% → 포함

    def test_below_improvement_ratio_excluded(self):
        stats = {
            "청결": {"positive": 50, "negative": 19, "total": 100},
        }
        _, improvements, _, _ = TagStatsCalculator.compute_strengths_improvements(stats)
        assert len(improvements) == 0  # 19% < 20% → 제외

    def test_empty_stats(self):
        strengths, improvements, s_detail, i_detail = (
            TagStatsCalculator.compute_strengths_improvements({})
        )
        assert strengths == []
        assert improvements == []

    def test_sorted_by_ratio_descending(self):
        stats = {
            "가격": {"positive": 70, "negative": 10, "total": 100},
            "직원친절": {"positive": 90, "negative": 5, "total": 100},
            "청결": {"positive": 80, "negative": 8, "total": 100},
        }
        _, _, s_detail, _ = TagStatsCalculator.compute_strengths_improvements(stats)
        ratios = [d["ratio"] for d in s_detail]
        assert ratios == sorted(ratios, reverse=True)


# ── compute_trend ─────────────────────────────────────


class TestComputeTrend:
    def test_up_direction(self):
        result = TagStatsCalculator.compute_trend(
            {"직원친절": {"positive": 90, "total": 100}},
            {"직원친절": {"positive": 50, "total": 100}},
            {"positive": 90, "negative": 10, "total": 100},
            {"positive": 50, "negative": 50, "total": 100},
        )
        trends = result["category_trends"]
        assert len(trends) == 1
        assert trends[0]["direction"] == "up"
        assert trends[0]["change"] == 40

    def test_down_direction(self):
        result = TagStatsCalculator.compute_trend(
            {"직원친절": {"positive": 30, "total": 100}},
            {"직원친절": {"positive": 80, "total": 100}},
            {"positive": 30, "negative": 70, "total": 100},
            {"positive": 80, "negative": 20, "total": 100},
        )
        trends = result["category_trends"]
        assert trends[0]["direction"] == "down"

    def test_stable_direction(self):
        result = TagStatsCalculator.compute_trend(
            {"직원친절": {"positive": 70, "total": 100}},
            {"직원친절": {"positive": 72, "total": 100}},
            {"positive": 70, "total": 100},
            {"positive": 72, "total": 100},
        )
        trends = result["category_trends"]
        assert trends[0]["direction"] == "stable"
        assert -2 <= trends[0]["change"] <= 2

    def test_boundary_up_at_3(self):
        result = TagStatsCalculator.compute_trend(
            {"직원친절": {"positive": 53, "total": 100}},
            {"직원친절": {"positive": 50, "total": 100}},
            {"positive": 53, "total": 100},
            {"positive": 50, "total": 100},
        )
        assert result["category_trends"][0]["direction"] == "up"

    def test_boundary_down_at_minus3(self):
        result = TagStatsCalculator.compute_trend(
            {"직원친절": {"positive": 47, "total": 100}},
            {"직원친절": {"positive": 50, "total": 100}},
            {"positive": 47, "total": 100},
            {"positive": 50, "total": 100},
        )
        assert result["category_trends"][0]["direction"] == "down"

    def test_new_category_in_current(self):
        """현재에만 있는 카테고리 → 이전 0% 기준 변화"""
        result = TagStatsCalculator.compute_trend(
            {"새카테고리": {"positive": 80, "total": 100}},
            {},
            {"positive": 80, "total": 100},
            {"positive": 0, "total": 0},
        )
        trends = result["category_trends"]
        assert len(trends) == 1
        assert trends[0]["direction"] == "up"

    def test_empty_both_periods(self):
        result = TagStatsCalculator.compute_trend(
            {}, {},
            {"positive": 0, "total": 0},
            {"positive": 0, "total": 0},
        )
        assert result["category_trends"] == []
        assert result["overall_positive_change"] == 0

    def test_overall_change_calculated(self):
        result = TagStatsCalculator.compute_trend(
            {"직원친절": {"positive": 80, "total": 100}},
            {"직원친절": {"positive": 60, "total": 100}},
            {"positive": 80, "negative": 20, "total": 100},
            {"positive": 60, "negative": 40, "total": 100},
        )
        assert result["overall_positive_change"] == 20
        assert result["overall_negative_change"] == -20

    def test_sorted_by_abs_change_descending(self):
        result = TagStatsCalculator.compute_trend(
            {
                "가격": {"positive": 80, "total": 100},
                "직원친절": {"positive": 50, "total": 100},
                "청결": {"positive": 60, "total": 100},
            },
            {
                "가격": {"positive": 50, "total": 100},
                "직원친절": {"positive": 90, "total": 100},
                "청결": {"positive": 55, "total": 100},
            },
            {"positive": 60, "total": 100},
            {"positive": 60, "total": 100},
        )
        trends = result["category_trends"]
        abs_changes = [abs(t["change"]) for t in trends]
        assert abs_changes == sorted(abs_changes, reverse=True)


# ── compute_top_tags ──────────────────────────────────


class TestComputeTopTags:
    def _make_tag_detail(self, tag_name, category, positive, negative):
        return {
            "tag_name": tag_name,
            "category_name": category,
            "positive": positive,
            "negative": negative,
            "total": positive + negative,
        }

    def test_basic_top_positive(self):
        details = [
            self._make_tag_detail("친절", "직원친절", 50, 5),
            self._make_tag_detail("가격", "가격", 30, 10),
        ]
        top_pos, top_neg, top_detail = TagStatsCalculator.compute_top_tags(details)
        assert len(top_pos) >= 1
        assert top_pos[0].count >= top_pos[-1].count  # 내림차순

    def test_vehicle_categories_excluded(self):
        """vehicle 카테고리는 top_tags에서 제외"""
        details = [
            self._make_tag_detail("청결", "청결", 50, 5),  # vehicle
            self._make_tag_detail("외관", "외관", 40, 10),  # vehicle
            self._make_tag_detail("친절", "직원친절", 30, 5),  # affiliate
        ]
        top_pos, _, _ = TagStatsCalculator.compute_top_tags(details)
        categories = [t.category_name for t in top_pos]
        assert "청결" not in categories
        assert "외관" not in categories

    def test_max_five_results(self):
        details = [
            self._make_tag_detail(f"tag{i}", "직원친절", 50 - i, 5)
            for i in range(10)
        ]
        top_pos, _, _ = TagStatsCalculator.compute_top_tags(details)
        assert len(top_pos) <= 5

    def test_zero_negative_excluded_from_top_negative(self):
        details = [
            self._make_tag_detail("친절", "직원친절", 50, 0),
        ]
        _, top_neg, _ = TagStatsCalculator.compute_top_tags(details)
        assert len(top_neg) == 0

    def test_empty_details(self):
        top_pos, top_neg, top_detail = TagStatsCalculator.compute_top_tags([])
        assert top_pos == []
        assert top_neg == []
        assert top_detail == []

    def test_same_category_tags_aggregated(self):
        """동일 카테고리 태그는 합산"""
        details = [
            self._make_tag_detail("친절", "직원친절", 30, 5),
            self._make_tag_detail("안내", "직원친절", 20, 3),
        ]
        top_pos, _, top_detail = TagStatsCalculator.compute_top_tags(details)
        # 직원친절 카테고리: positive 합산 50
        assert len(top_pos) == 1
        assert top_pos[0].count == 50

    def test_ratio_calculation(self):
        details = [
            self._make_tag_detail("친절", "직원친절", 80, 20),
        ]
        top_pos, top_neg, _ = TagStatsCalculator.compute_top_tags(details)
        assert top_pos[0].ratio == 80  # 80/100 * 100
        assert top_neg[0].ratio == 20  # 20/100 * 100
