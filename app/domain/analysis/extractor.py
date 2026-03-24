"""
키워드 추출기 (Kiwi 기반)
"""

from __future__ import annotations

import re

from core.stopwords import LexiconConfig
from domain.analysis._singletons import kiwi_tokenize


class KeywordExtractor:
    """
    Kiwi 기반 키워드 추출기

    한국어 리뷰 텍스트에서 명사(NNG, NNP)와 형용사(VA)를 추출합니다.
    불용어 필터링을 통해 의미 있는 키워드만 반환합니다.
    """

    def __init__(
        self,
        stopwords: set[str] | None = None,
        min_length: int = 2,
        pos_tags: list[str] | None = None,
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
        """Kiwi 인스턴스 (싱글턴 팩토리 사용)"""
        if self._kiwi_available is None:
            from domain.analysis._singletons import get_kiwi

            self._kiwi = get_kiwi()
            self._kiwi_available = self._kiwi is not None

        return self._kiwi

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
            for token in kiwi_tokenize(text):
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


