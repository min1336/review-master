"""sync_service._filter_misrouted_reviews 단위 테스트

오배정 리뷰 필터링: branch_id별 dominant company 기반 방어 로직
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from services.sync_service import _filter_misrouted_reviews


def _make_review(review_id, branch_id, company_name):
    return {
        "review_id": review_id,
        "branch_id": branch_id,
        "company_name": company_name,
    }


class TestFilterMisroutedReviews:
    def test_all_same_company_no_filtering(self):
        reviews = [
            _make_review(1, 100, "스마트렌트카"),
            _make_review(2, 100, "스마트렌트카"),
            _make_review(3, 100, "스마트렌트카"),
        ]
        filtered, dropped = _filter_misrouted_reviews(reviews)
        assert dropped == 0
        assert len(filtered) == 3

    def test_dominant_80_percent_filters_minority(self):
        # 10 reviews: 9 dominant (90%) + 1 minority → 1 dropped
        reviews = [_make_review(i, 100, "스마트렌트카") for i in range(9)]
        reviews.append(_make_review(9, 100, "달러렌트카"))
        filtered, dropped = _filter_misrouted_reviews(reviews)
        assert dropped == 1
        assert len(filtered) == 9

    def test_below_80_percent_no_filtering(self):
        # 5 reviews: 3 dominant (60%) + 2 minority → no filtering
        reviews = [
            _make_review(1, 100, "A업체"),
            _make_review(2, 100, "A업체"),
            _make_review(3, 100, "A업체"),
            _make_review(4, 100, "B업체"),
            _make_review(5, 100, "C업체"),
        ]
        filtered, dropped = _filter_misrouted_reviews(reviews)
        assert dropped == 0
        assert len(filtered) == 5

    def test_exactly_80_percent_filters(self):
        # 5 reviews: 4 dominant (80%) + 1 minority → 1 dropped
        reviews = [_make_review(i, 100, "스마트렌트카") for i in range(4)]
        reviews.append(_make_review(4, 100, "달러렌트카"))
        filtered, dropped = _filter_misrouted_reviews(reviews)
        assert dropped == 1
        assert len(filtered) == 4

    def test_multiple_branches_independent(self):
        reviews = [
            # branch 100: 스마트 3, 달러 1 → 75% → no filtering
            _make_review(1, 100, "스마트렌트카"),
            _make_review(2, 100, "스마트렌트카"),
            _make_review(3, 100, "스마트렌트카"),
            _make_review(4, 100, "달러렌트카"),
            # branch 200: A 5, B 1 → 83% → B filtered
            _make_review(5, 200, "A업체"),
            _make_review(6, 200, "A업체"),
            _make_review(7, 200, "A업체"),
            _make_review(8, 200, "A업체"),
            _make_review(9, 200, "A업체"),
            _make_review(10, 200, "B업체"),
        ]
        filtered, dropped = _filter_misrouted_reviews(reviews)
        assert dropped == 1  # only branch 200's B업체
        assert len(filtered) == 9

    def test_empty_company_name_not_filtered(self):
        reviews = [
            _make_review(1, 100, "스마트렌트카"),
            _make_review(2, 100, "스마트렌트카"),
            _make_review(3, 100, ""),  # empty → not counted, passes through
        ]
        filtered, dropped = _filter_misrouted_reviews(reviews)
        assert dropped == 0
        assert len(filtered) == 3

    def test_empty_list(self):
        filtered, dropped = _filter_misrouted_reviews([])
        assert dropped == 0
        assert filtered == []

    def test_athena_field_names(self):
        # Athena API uses 지점번호, 예약_업체명
        reviews = [
            {"review_id": 1, "지점번호": 100, "예약_업체명": "스마트렌트카"},
            {"review_id": 2, "지점번호": 100, "예약_업체명": "스마트렌트카"},
            {"review_id": 3, "지점번호": 100, "예약_업체명": "스마트렌트카"},
            {"review_id": 4, "지점번호": 100, "예약_업체명": "스마트렌트카"},
            {"review_id": 5, "지점번호": 100, "예약_업체명": "달러렌트카"},
        ]
        filtered, dropped = _filter_misrouted_reviews(reviews)
        assert dropped == 1

    def test_invalid_branch_id_passes_through(self):
        reviews = [
            {"review_id": 1, "branch_id": "invalid", "company_name": "A"},
            _make_review(2, 100, "스마트렌트카"),
        ]
        filtered, dropped = _filter_misrouted_reviews(reviews)
        assert dropped == 0
        assert len(filtered) == 2

    def test_none_branch_id_passes_through(self):
        reviews = [
            {"review_id": 1, "branch_id": None, "company_name": "A"},
            _make_review(2, 100, "스마트렌트카"),
        ]
        filtered, dropped = _filter_misrouted_reviews(reviews)
        assert dropped == 0
        assert len(filtered) == 2
