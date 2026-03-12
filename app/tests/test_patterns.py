"""patterns.py 단위 테스트

TAG_REGISTRY 파생 상수, 유틸리티 함수, 정규식 패턴 검증
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from domain.analysis.patterns import (
    AFFILIATE_CATEGORIES,
    ASPECT_KEYWORDS,
    CATEGORY_DEFAULT_TAG,
    DOUBLE_NEGATION_REGEX,
    LEGACY_CATEGORY_MAP,
    NEGATIVE_REGEX,
    POSITIVE_EXCEPTION_REGEX,
    POSITIVE_REGEX,
    RULE_BASED_TAG_MAPPING,
    TAG_COLORS,
    TAG_DESCRIPTIONS,
    TAG_REGISTRY,
    TAG_TO_CATEGORY,
    TAG_TO_CATEGORY_COLOR,
    VEHICLE_CATEGORIES,
    extract_stem,
    get_tag_for_keyword,
    is_negative_keyword,
    normalize_category_name,
    resolve_tag_category,
)


# ── TAG_REGISTRY 구조 검증 ──────────────────────────────


class TestTagRegistry:
    def test_registry_has_expected_categories(self):
        expected = {
            "직원친절", "외관", "가격", "청결",
            "사고 처리", "주유비", "배달/배차", "반납/픽업", "위치/접근성",
        }
        assert set(TAG_REGISTRY.keys()) == expected

    def test_each_category_has_required_fields(self):
        for name, cat in TAG_REGISTRY.items():
            assert cat.group in ("affiliate", "vehicle"), f"{name}: invalid group"
            assert cat.color.startswith("#"), f"{name}: color missing #"
            assert cat.default_tag, f"{name}: missing default_tag"
            assert cat.description, f"{name}: missing description"
            assert cat.positive_label, f"{name}: missing positive_label"
            assert cat.negative_label, f"{name}: missing negative_label"
            assert len(cat.tags) > 0, f"{name}: no tags"

    def test_default_tag_belongs_to_category(self):
        for name, cat in TAG_REGISTRY.items():
            assert cat.default_tag in cat.tags, (
                f"{name}: default_tag '{cat.default_tag}' not in tags"
            )

    def test_total_tag_count(self):
        total = sum(len(cat.tags) for cat in TAG_REGISTRY.values())
        assert total == 52

    def test_affiliate_vehicle_partition(self):
        all_cats = set(TAG_REGISTRY.keys())
        assert AFFILIATE_CATEGORIES | VEHICLE_CATEGORIES == all_cats
        assert AFFILIATE_CATEGORIES & VEHICLE_CATEGORIES == set()


# ── 파생 상수 검증 ────────────────────────────────────


class TestDerivedConstants:
    def test_tag_to_category_covers_all_tags(self):
        for cat_name, cat in TAG_REGISTRY.items():
            for tag_name in cat.tags:
                assert TAG_TO_CATEGORY[tag_name] == cat_name

    def test_tag_to_category_color_matches(self):
        for cat_name, cat in TAG_REGISTRY.items():
            for tag_name in cat.tags:
                assert TAG_TO_CATEGORY_COLOR[tag_name] == cat.color

    def test_rule_based_tag_mapping_count(self):
        assert len(RULE_BASED_TAG_MAPPING) == 52

    def test_aspect_keywords_per_category(self):
        assert len(ASPECT_KEYWORDS) == len(TAG_REGISTRY)
        for cat_name in TAG_REGISTRY:
            assert cat_name in ASPECT_KEYWORDS

    def test_tag_descriptions_per_category(self):
        assert set(TAG_DESCRIPTIONS.keys()) == set(TAG_REGISTRY.keys())

    def test_tag_colors_per_category(self):
        assert set(TAG_COLORS.keys()) == set(TAG_REGISTRY.keys())

    def test_category_default_tag_per_category(self):
        assert set(CATEGORY_DEFAULT_TAG.keys()) == set(TAG_REGISTRY.keys())


# ── normalize_category_name ───────────────────────────


class TestNormalizeCategoryName:
    @pytest.mark.parametrize("legacy,expected", [
        ("직원이 친절함", "직원친절"),
        ("차량외관이 좋음", "외관"),
        ("가격이 저렴함", "가격"),
        ("차량이 청결함", "청결"),
        ("사고 처리를 잘해줌", "사고 처리"),
        ("주유비 부담 없음", "주유비"),
        ("배달 서비스가 우수함", "배달/배차"),
        ("배달", "배달/배차"),
    ])
    def test_legacy_mappings(self, legacy, expected):
        assert normalize_category_name(legacy) == expected

    def test_current_name_passthrough(self):
        assert normalize_category_name("직원친절") == "직원친절"
        assert normalize_category_name("청결") == "청결"

    def test_empty_and_none(self):
        assert normalize_category_name("") == ""
        assert normalize_category_name(None) == ""


# ── resolve_tag_category ──────────────────────────────


class TestResolveTagCategory:
    def test_known_tag_returns_registry_category(self):
        assert resolve_tag_category("친절") == "직원친절"
        assert resolve_tag_category("청결") == "청결"
        assert resolve_tag_category("가격") == "가격"
        assert resolve_tag_category("딜리버리") == "배달/배차"

    def test_unknown_tag_falls_back_to_db_category(self):
        assert resolve_tag_category("알수없는태그", "직원친절") == "직원친절"

    def test_unknown_tag_normalizes_legacy_db_category(self):
        assert resolve_tag_category("새태그", "배달 서비스가 우수함") == "배달/배차"

    def test_unknown_tag_empty_db_category(self):
        assert resolve_tag_category("알수없는태그", "") == ""

    def test_registry_priority_over_db(self):
        # "친절"은 TAG_REGISTRY에서 "직원친절"로 매핑됨
        # db_category가 다르더라도 레지스트리 우선
        assert resolve_tag_category("친절", "가격") == "직원친절"


# ── extract_stem ──────────────────────────────────────


class TestExtractStem:
    @pytest.mark.parametrize("keyword,expected", [
        ("친절한", "친절"),
        ("깨끗함", "깨끗"),
        ("불편했다", "불편"),
        ("만족합니다", "만족"),
        ("편리해요", "편리"),
        ("서비스", "서비스"),
        ("좋았습니다", "좋았습니다"),  # "았습니다" 는 접미사 목록에 없어 원본 유지
    ])
    def test_suffix_removal(self, keyword, expected):
        assert extract_stem(keyword) == expected

    def test_empty_string(self):
        assert extract_stem("") == ""

    def test_single_char_preserved(self):
        # 1글자에서 접미사 제거 시 빈 문자열이 되면 원본 반환
        assert extract_stem("한") == "한"


# ── is_negative_keyword ───────────────────────────────


class TestIsNegativeKeyword:
    @pytest.mark.parametrize("keyword", [
        "불친절", "불편", "비싸", "더럽", "최악", "실망", "별로",
        "느리", "지저분", "냄새", "고장",
    ])
    def test_negative_keywords_detected(self, keyword):
        assert is_negative_keyword(keyword) is True

    @pytest.mark.parametrize("keyword", [
        "친절", "깨끗", "좋은", "만족", "편리",
    ])
    def test_positive_keywords_not_negative(self, keyword):
        assert is_negative_keyword(keyword) is False

    def test_empty_string(self):
        assert is_negative_keyword("") is False


# ── get_tag_for_keyword ───────────────────────────────


class TestGetTagForKeyword:
    @pytest.mark.parametrize("keyword,expected_tag", [
        ("친절", "친절"),
        ("불친절", "친절"),
        ("에어컨", "옵션"),
        ("주유", "주유"),
        ("보험", "보험/보장"),
        ("스크래치", "차량외관"),
        ("배차", "배차/시간"),
    ])
    def test_known_keywords(self, keyword, expected_tag):
        assert get_tag_for_keyword(keyword) == expected_tag

    def test_unknown_keyword_returns_etc(self):
        assert get_tag_for_keyword("asdfghjkl") == "기타"

    def test_empty_returns_etc(self):
        assert get_tag_for_keyword("") == "기타"


# ── 정규식 패턴 검증 ─────────────────────────────────


class TestRegexPatterns:
    def test_negative_regex_matches(self):
        assert NEGATIVE_REGEX.search("불친절한 직원")
        assert NEGATIVE_REGEX.search("차가 더러웠어요")
        assert NEGATIVE_REGEX.search("가격이 비싸요")

    def test_positive_regex_matches(self):
        assert POSITIVE_REGEX.search("직원이 친절해요")
        assert POSITIVE_REGEX.search("차가 깨끗했습니다")
        assert POSITIVE_REGEX.search("가격이 저렴해요")

    def test_double_negation_matches(self):
        assert DOUBLE_NEGATION_REGEX.search("불편한 점이 없었어요")
        assert DOUBLE_NEGATION_REGEX.search("문제없이 잘 이용했습니다")
        assert DOUBLE_NEGATION_REGEX.search("나쁘지 않았어요")

    def test_positive_exception_matches(self):
        assert POSITIVE_EXCEPTION_REGEX.search("틀림없이 좋아요")
        assert POSITIVE_EXCEPTION_REGEX.search("부담없이 이용")
        assert POSITIVE_EXCEPTION_REGEX.search("문제없어요")
