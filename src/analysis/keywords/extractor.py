"""
키워드 추출기 (MeCab 기반)
"""
import re
from typing import List, Set, Optional
from ...config.stopwords import LexiconConfig


class KeywordExtractor:
    """
    MeCab 기반 키워드 추출기

    한국어 리뷰 텍스트에서 명사(NNG, NNP)와 형용사(VA)를 추출합니다.
    불용어 필터링을 통해 의미 있는 키워드만 반환합니다.
    """

    def __init__(
        self,
        stopwords: Set[str] = None,
        min_length: int = 2,
        pos_tags: List[str] = None
    ):
        """
        Args:
            stopwords: 불용어 집합 (기본값: LexiconConfig.STOP_WORDS)
            min_length: 최소 키워드 길이 (기본값: 2)
            pos_tags: 추출할 품사 태그 (기본값: ['NNG', 'NNP', 'VA'])
        """
        self.stopwords = stopwords or LexiconConfig.STOP_WORDS
        self.min_length = min_length
        self.pos_tags = pos_tags or ['NNG', 'NNP', 'VA']

        # MeCab 초기화 (지연 로딩)
        self._mecab = None
        self._mecab_available = None

    @property
    def mecab(self):
        """MeCab 인스턴스 (지연 로딩)"""
        if self._mecab_available is None:
            try:
                import mecab
                self._mecab = mecab.MeCab()
                self._mecab_available = True
            except ImportError:
                self._mecab_available = False

        return self._mecab

    @property
    def is_mecab_available(self) -> bool:
        """MeCab 사용 가능 여부"""
        _ = self.mecab  # 초기화 트리거
        return self._mecab_available

    def extract(self, text: str) -> List[str]:
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

        # MeCab 사용 가능시
        if self.mecab:
            return self._extract_with_mecab(text)

        # 정규식 폴백
        return self._extract_with_regex(text)

    def _extract_with_mecab(self, text: str) -> List[str]:
        """MeCab을 사용한 키워드 추출"""
        try:
            keywords = []
            for token in self.mecab.parse(text):
                pos = token.pos
                word = token.surface

                # 지정된 품사만 추출
                if any(pos.startswith(tag) for tag in self.pos_tags):
                    if len(word) >= self.min_length and word not in self.stopwords:
                        keywords.append(word)

            return keywords
        except Exception:
            return self._extract_with_regex(text)

    def _extract_with_regex(self, text: str) -> List[str]:
        """정규식을 사용한 폴백 키워드 추출"""
        words = re.findall(r'[가-힣]{2,}', text)
        return [w for w in words if w not in self.stopwords and len(w) >= self.min_length]

    def extract_batch(self, texts: List[str]) -> List[List[str]]:
        """
        배치 키워드 추출

        Args:
            texts: 텍스트 리스트

        Returns:
            키워드 리스트의 리스트
        """
        return [self.extract(text) for text in texts]

    def extract_batch_parallel(
        self,
        texts: List[str],
        n_jobs: int = -1,
        verbose: int = 0
    ) -> List[List[str]]:
        """
        병렬 배치 키워드 추출 (joblib 사용)

        Args:
            texts: 텍스트 리스트
            n_jobs: 병렬 작업 수 (-1: 모든 CPU)
            verbose: 상세 출력 레벨

        Returns:
            키워드 리스트의 리스트
        """
        try:
            from joblib import Parallel, delayed
        except ImportError:
            print("⚠️ joblib 미설치 - 순차 처리 사용")
            return self.extract_batch(texts)

        # 정규식 폴백 함수 (MeCab이 워커에서 초기화 안될 수 있음)
        def extract_single(text: str, stopwords: set, min_length: int) -> List[str]:
            import re
            if not text or not isinstance(text, str):
                return []
            text = text.strip()
            if not text:
                return []

            # MeCab 시도
            try:
                import mecab
                m = mecab.MeCab()
                keywords = []
                for token in m.parse(text):
                    pos = token.pos
                    word = token.surface
                    if pos.startswith('NNG') or pos.startswith('NNP') or pos.startswith('VA'):
                        if len(word) >= min_length and word not in stopwords:
                            keywords.append(word)
                return keywords
            except:
                # 정규식 폴백
                words = re.findall(r'[가-힣]{2,}', text)
                return [w for w in words if w not in stopwords and len(w) >= min_length]

        return Parallel(n_jobs=n_jobs, verbose=verbose)(
            delayed(extract_single)(text, self.stopwords, self.min_length)
            for text in texts
        )

    def add_stopwords(self, words: Set[str]):
        """불용어 추가"""
        self.stopwords = self.stopwords | words

    def remove_stopwords(self, words: Set[str]):
        """불용어 제거"""
        self.stopwords = self.stopwords - words
