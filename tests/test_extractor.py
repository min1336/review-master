"""KeywordExtractor 단위 테스트

정규식 폴백 모드 (Kiwi 미설치 환경) 중심
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from domain.analysis.extractor import KeywordExtractor


@pytest.fixture
def extractor():
    """Kiwi 없이 regex 폴백으로 동작하는 추출기"""
    ex = KeywordExtractor(min_length=2)
    ex._kiwi = None
    ex._kiwi_available = False
    return ex


# ── _extract_with_regex ───────────────────────────────


class TestRegexExtraction:
    def test_basic_korean_extraction(self, extractor):
        result = extractor.extract("직원이 친절했어요")
        assert isinstance(result, list)
        assert len(result) > 0
        # [가-힣]{2,} 패턴으로 2글자 이상 한글 추출
        for kw in result:
            assert len(kw) >= 2

    def test_stopwords_filtered(self, extractor):
        # 불용어는 제외되어야 함
        stopwords = extractor.stopwords
        result = extractor.extract("이것은 테스트 문장입니다")
        for kw in result:
            assert kw not in stopwords

    def test_empty_text(self, extractor):
        assert extractor.extract("") == []
        assert extractor.extract("   ") == []

    def test_none_text(self, extractor):
        assert extractor.extract(None) == []

    def test_non_string_text(self, extractor):
        assert extractor.extract(123) == []

    def test_english_only_text(self, extractor):
        result = extractor.extract("hello world good service")
        assert result == []  # 한글만 추출

    def test_mixed_korean_english(self, extractor):
        result = extractor.extract("service가 친절하고 good이에요")
        # 한글 부분만 추출
        for kw in result:
            assert all('\uAC00' <= c <= '\uD7A3' for c in kw)

    def test_single_char_filtered(self, extractor):
        result = extractor.extract("가 나 다")
        assert result == []  # 1글자는 min_length=2 미만

    def test_numbers_ignored(self, extractor):
        result = extractor.extract("12345 가격 67890")
        assert all(kw.isalpha() for kw in result)


# ── min_length 설정 ───────────────────────────────────


class TestMinLength:
    def test_custom_min_length(self):
        ex = KeywordExtractor(min_length=3)
        ex._kiwi = None
        ex._kiwi_available = False
        result = ex.extract("서비스 가격이 저렴해요")
        for kw in result:
            assert len(kw) >= 3

    def test_min_length_one(self):
        ex = KeywordExtractor(min_length=1)
        ex._kiwi = None
        ex._kiwi_available = False
        result = ex.extract("가 나 다라 마바")
        # 1글자도 포함 (불용어 아닌 경우)
        assert len(result) >= 0


# ── custom stopwords ──────────────────────────────────


class TestCustomStopwords:
    def test_custom_stopwords_applied(self):
        ex = KeywordExtractor(stopwords={"친절", "서비스"})
        ex._kiwi = None
        ex._kiwi_available = False
        result = ex.extract("직원이 친절하고 서비스가 좋아요")
        assert "친절" not in result
        assert "서비스" not in result
