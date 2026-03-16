"""chunker.py 단위 테스트

ClauseChunker: 접속사/연결어미/문장부호 기준 절 분리
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from domain.analysis.chunker import ClauseChunker


@pytest.fixture
def chunker():
    return ClauseChunker(use_punctuation=True)


@pytest.fixture
def chunker_no_punct():
    return ClauseChunker(use_punctuation=False)


class TestClauseChunkerBasic:
    def test_empty_text(self, chunker):
        assert chunker.chunk("") == []
        assert chunker.chunk("  ") == []
        assert chunker.chunk(None) == []

    def test_short_text_below_min_length(self):
        c = ClauseChunker(min_chunk_length=5)
        assert c.chunk("좋아") == []

    def test_single_clause(self, chunker):
        result = chunker.chunk("직원이 친절했어요")
        assert len(result) >= 1
        assert "친절" in result[0]


class TestConjunctionSplitting:
    def test_split_by_conjunction_geurigo(self, chunker_no_punct):
        result = chunker_no_punct.chunk("직원이 친절했어요 그리고 차가 깨끗했어요")
        assert len(result) == 2

    def test_split_by_conjunction_hajiman(self, chunker_no_punct):
        result = chunker_no_punct.chunk("직원이 친절했어요 하지만 차가 더러웠어요")
        assert len(result) == 2

    def test_split_by_conjunction_geureonde(self, chunker_no_punct):
        result = chunker_no_punct.chunk("가격이 싸요 그런데 차가 좀 낡았어요")
        assert len(result) == 2


class TestConnectiveSplitting:
    def test_split_by_jiman(self, chunker_no_punct):
        result = chunker_no_punct.chunk("친절했지만 차가 더러웠어요")
        assert len(result) == 2

    def test_split_by_neunde(self, chunker_no_punct):
        result = chunker_no_punct.chunk("좋은데 가격이 비싸요")
        assert len(result) == 2

    def test_split_by_eoseo(self, chunker_no_punct):
        # "워서"는 "어서" 패턴에 매칭되지 않음 (ㅂ불규칙)
        # 정확히 "어서"가 포함된 케이스 사용
        result = chunker_no_punct.chunk("멀어서 불편했어요")
        assert len(result) == 2


class TestPunctuationSplitting:
    def test_period_split(self, chunker):
        result = chunker.chunk("친절했어요. 차도 깨끗했어요.")
        assert len(result) >= 2

    def test_comma_split(self, chunker):
        result = chunker.chunk("친절하고, 깨끗하고, 저렴했어요")
        assert len(result) >= 2


class TestComplexReview:
    def test_multi_clause_review(self, chunker):
        review = "직원이 친절했어요. 하지만 차가 좀 더러웠고, 가격도 비쌌어요"
        result = chunker.chunk(review)
        assert len(result) >= 2

    def test_preserves_all_content(self, chunker_no_punct):
        review = "직원이 친절했지만 차가 더러웠어요"
        result = chunker_no_punct.chunk(review)
        combined = " ".join(result)
        assert "친절" in combined
        assert "더러" in combined
