"""schemas/common.py 유틸 테스트

API Envelope, 날짜 파싱/검증, period 프리셋 변환
"""

import sys
import os
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi import HTTPException

from schemas.common import (
    api_list_response,
    api_response,
    resolve_period,
    validate_date_range_d,
)
from api.v1.endpoints._common import sanitize_pdf_filename


# ── api_response ──────────────────────────────────────


class TestApiResponse:
    def test_basic_envelope(self):
        result = api_response({"key": "value"})
        assert result["success"] is True
        assert result["data"] == {"key": "value"}

    def test_none_data(self):
        result = api_response(None)
        assert result["success"] is True
        assert result["data"] is None

    def test_list_data(self):
        result = api_response([1, 2, 3])
        assert result["data"] == [1, 2, 3]


# ── api_list_response ────────────────────────────────


class TestApiListResponse:
    def test_basic_list_envelope(self):
        result = api_list_response([1, 2, 3])
        assert result["success"] is True
        assert result["data"] == [1, 2, 3]
        assert result["count"] == 3

    def test_explicit_count_overrides(self):
        result = api_list_response([1, 2], count=10)
        assert result["count"] == 10

    def test_total_and_pagination(self):
        result = api_list_response([1, 2], total=100, limit=10, offset=0)
        assert result["total"] == 100
        assert result["has_next"] is True

    def test_last_page_has_next_false(self):
        result = api_list_response([1], total=10, limit=10, offset=5)
        assert result["has_next"] is False

    def test_no_total_no_has_next(self):
        result = api_list_response([1, 2])
        assert "total" not in result
        assert "has_next" not in result

    def test_empty_list(self):
        result = api_list_response([])
        assert result["count"] == 0
        assert result["data"] == []


# ── validate_date_range_d ─────────────────────────────


class TestValidateDateRangeD:
    def test_valid_range(self):
        # 예외 없이 통과
        validate_date_range_d(date(2026, 1, 1), date(2026, 3, 1))

    def test_same_date_valid(self):
        validate_date_range_d(date(2026, 1, 1), date(2026, 1, 1))

    def test_reversed_range_raises(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_date_range_d(date(2026, 3, 1), date(2026, 1, 1))
        assert exc_info.value.status_code == 400

    def test_none_start_valid(self):
        validate_date_range_d(None, date(2026, 3, 1))

    def test_none_end_valid(self):
        validate_date_range_d(date(2026, 1, 1), None)

    def test_both_none_valid(self):
        validate_date_range_d(None, None)


# ── resolve_period ────────────────────────────────────


class TestResolvePeriod:
    @pytest.mark.parametrize("period", ["1m", "3m", "6m", "12m", "1y", "all"])
    def test_valid_periods(self, period):
        start, end = resolve_period(period)
        assert start < end

    def test_invalid_period_raises(self):
        with pytest.raises(ValueError):
            resolve_period("invalid")

    def test_all_starts_from_2020(self):
        start, end = resolve_period("all")
        assert start.year == 2020
        assert start.month == 1

    def test_1m_roughly_30_days(self):
        start, end = resolve_period("1m")
        diff = (end - start).days
        assert 28 <= diff <= 31

    def test_12m_equals_1y(self):
        start_12m, _ = resolve_period("12m")
        start_1y, _ = resolve_period("1y")
        assert start_12m == start_1y


# ── sanitize_pdf_filename ──────────────────────────────


class TestSanitizePdfFilename:
    def test_windows_reserved_chars_replaced(self):
        for ch in r'\/:*?"<>|':
            result = sanitize_pdf_filename(ch)
            assert result == "_", f"char {ch!r} should become '_', got {result!r}"

    def test_clean_name_unchanged(self):
        name = "2026-03-report_final"
        assert sanitize_pdf_filename(name) == name

    def test_empty_string(self):
        assert sanitize_pdf_filename("") == ""

    def test_only_forbidden_chars(self):
        assert sanitize_pdf_filename("///") == "___"

    def test_multiple_consecutive_forbidden_chars(self):
        result = sanitize_pdf_filename('report<2026>:final*')
        assert result == "report_2026__final_"
