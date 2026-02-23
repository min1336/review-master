"""
키워드 추출기 (Kiwi 기반)
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from core.stopwords import LexiconConfig

if TYPE_CHECKING:
    from .chunker import ClauseChunker


class KeywordExtractor:
    """
    Kiwi 기반 키워드 추출기

    한국어 리뷰 텍스트에서 명사(NNG, NNP)와 형용사(VA)를 추출합니다.
    불용어 필터링을 통해 의미 있는 키워드만 반환합니다.
    """

    def __init__(
        self,
        stopwords: set[str] = None,
        min_length: int = 2,
        pos_tags: list[str] = None,
    ):
        """
        Args:
            stopwords: 불용어 집합 (기본값: LexiconConfig.STOP_WORDS)
            min_length: 최소 키워드 길이 (기본값: 2)
            pos_tags: 추출할 품사 태그 (기본값: ['NNG', 'NNP', 'VA', 'XR'])
        """
        self.stopwords = stopwords or LexiconConfig.STOP_WORDS
        self.min_length = min_length
        # XR(어근): 깨끗, 저렴 등 / IC(감탄사): 강추, 대박 등
        self.pos_tags = pos_tags or ["NNG", "NNP", "VA", "XR", "IC"]

        # Kiwi 초기화 (지연 로딩)
        self._kiwi = None
        self._kiwi_available = None

    @property
    def kiwi(self):
        """Kiwi 인스턴스 (지연 로딩)"""
        if self._kiwi_available is None:
            try:
                from kiwipiepy import Kiwi

                self._kiwi = Kiwi()
                self._kiwi_available = True
            except ImportError:
                self._kiwi_available = False

        return self._kiwi

    @property
    def is_kiwi_available(self) -> bool:
        """Kiwi 사용 가능 여부"""
        _ = self.kiwi  # 초기화 트리거
        return self._kiwi_available

    def extract(self, text: str) -> list[str]:
        """
        텍스트에서 키워드 추출

        Args:
            text: 분석할 텍스트

        Returns:
            키워드 리스트
        """
        if not text or not isinstance(text, str):
            return []

        text = text.strip()
        if not text:
            return []

        # Kiwi 사용 가능시
        if self.kiwi:
            return self._extract_with_kiwi(text)

        # 정규식 폴백
        return self._extract_with_regex(text)

    def _extract_with_kiwi(self, text: str) -> list[str]:
        """Kiwi를 사용한 키워드 추출"""
        try:
            keywords = []
            for token in self.kiwi.tokenize(text):
                tag = token.tag
                word = token.form

                # 지정된 품사만 추출 (VA-I 등 하이픈 변형도 허용)
                base_tag = tag.split("-")[0]
                is_target_pos = tag in self.pos_tags or base_tag in self.pos_tags
                is_valid = len(word) >= self.min_length and word not in self.stopwords
                if is_target_pos and is_valid:
                    keywords.append(word)

            return keywords
        except Exception:
            return self._extract_with_regex(text)

    def _extract_with_regex(self, text: str) -> list[str]:
        """정규식을 사용한 폴백 키워드 추출"""
        words = re.findall(r"[가-힣]{2,}", text)
        return [
            w for w in words if w not in self.stopwords and len(w) >= self.min_length
        ]

    def extract_batch(self, texts: list[str]) -> list[list[str]]:
        """
        배치 키워드 추출

        Args:
            texts: 텍스트 리스트

        Returns:
            키워드 리스트의 리스트
        """
        return [self.extract(text) for text in texts]

    def add_stopwords(self, words: set[str]):
        """불용어 추가"""
        self.stopwords = self.stopwords | words

    def remove_stopwords(self, words: set[str]):
        """불용어 제거"""
        self.stopwords = self.stopwords - words

    # ========== 청킹 지원 메서드 ==========

    def extract_from_chunks(self, chunks: list[str]) -> list[list[str]]:
        """
        청크별 키워드 추출

        Args:
            chunks: 절 단위 청크 리스트

        Returns:
            청크별 키워드 리스트 [[청크1 키워드], [청크2 키워드], ...]
        """
        return [self.extract(chunk) for chunk in chunks]

    def extract_with_chunking(self, text: str, chunker: ClauseChunker = None) -> dict:
        """
        텍스트를 청킹 후 키워드 추출

        Args:
            text: 입력 텍스트
            chunker: ClauseChunker 인스턴스 (None이면 내부 생성)

        Returns:
            {
                'chunks': ['절1', '절2', ...],
                'keywords_per_chunk': [['키워드1'], ['키워드2'], ...],
                'flat_keywords': ['키워드1', '키워드2', ...]  # 중복 제거된 전체 키워드
            }
        """
        if not text or not text.strip():
            return {"chunks": [], "keywords_per_chunk": [], "flat_keywords": []}

        # 청커 초기화
        if chunker is None:
            from .chunker import ClauseChunker

            chunker = ClauseChunker()

        # 청킹
        chunks = chunker.chunk(text)

        # 청크별 키워드 추출
        keywords_per_chunk = self.extract_from_chunks(chunks)

        # 전체 키워드 (중복 제거, 순서 유지)
        seen = set()
        flat_keywords = []
        for kw_list in keywords_per_chunk:
            for kw in kw_list:
                if kw not in seen:
                    seen.add(kw)
                    flat_keywords.append(kw)

        return {
            "chunks": chunks,
            "keywords_per_chunk": keywords_per_chunk,
            "flat_keywords": flat_keywords,
        }

    def extract_batch_with_chunking(
        self, texts: list[str], chunker: ClauseChunker = None
    ) -> list[dict]:
        """
        배치 텍스트 청킹 + 키워드 추출

        Args:
            texts: 텍스트 리스트
            chunker: ClauseChunker 인스턴스

        Returns:
            각 텍스트별 extract_with_chunking 결과 리스트
        """
        if chunker is None:
            from .chunker import ClauseChunker

            chunker = ClauseChunker()

        return [self.extract_with_chunking(text, chunker) for text in texts]
