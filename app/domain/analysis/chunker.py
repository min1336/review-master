"""
절 단위 청킹 모듈
리뷰 텍스트를 접속사/연결어미 기준으로 분리
"""
import re
from typing import List


class ClauseChunker:
    """
    한국어 리뷰 절 분리기

    분리 기준:
    1. 접속사: 그리고, 하지만, 그런데, 그래서 등
    2. 연결어미: -고, -지만, -는데 등
    3. 문장 부호: 마침표, 쉼표 (선택적)
    """

    # 접속사 패턴
    CONJUNCTIONS = [
        '그리고', '하지만', '그런데', '그래서', '또한', '그러나',
        '그렇지만', '그러므로', '따라서', '반면', '대신', '다만',
        '또', '게다가', '더구나', '뿐만아니라', '아울러'
    ]

    # 연결어미 패턴 (문장 끝에서 분리점 역할)
    CONNECTIVE_PATTERNS = [
        r'(?<=[가-힣])고\s+',       # -고
        r'(?<=[가-힣])지만\s+',     # -지만
        r'(?<=[가-힣])는데\s+',     # -는데
        r'(?<=[가-힣])어서\s+',     # -어서
        r'(?<=[가-힣])아서\s+',     # -아서
        r'(?<=[가-힣])면서\s+',     # -면서
        r'(?<=[가-힣])니까\s+',     # -니까
        r'(?<=[가-힣])며\s+',       # -며
        r'(?<=[가-힣])ㄴ데\s+',     # -ㄴ데
        r'(?<=[가-힣])으며\s+',     # -으며
    ]

    def __init__(
        self,
        min_chunk_length: int = 3,
        use_punctuation: bool = False,
        keep_delimiter: bool = True
    ):
        """
        Args:
            min_chunk_length: 최소 청크 길이 (너무 짧은 청크 필터링)
            use_punctuation: 문장부호(마침표, 쉼표) 기준 분리 여부
            keep_delimiter: 분리 기준 접속사/어미를 청크에 포함할지 여부
        """
        self.min_chunk_length = min_chunk_length
        self.use_punctuation = use_punctuation
        self.keep_delimiter = keep_delimiter

        # 접속사 패턴 컴파일
        conjunction_pattern = '|'.join(
            rf'\s+{conj}\s+' for conj in self.CONJUNCTIONS
        )
        self._conjunction_regex = re.compile(conjunction_pattern)

        # 연결어미 패턴 컴파일
        connective_pattern = '|'.join(self.CONNECTIVE_PATTERNS)
        self._connective_regex = re.compile(connective_pattern)

        # 문장부호 패턴
        self._punctuation_regex = re.compile(r'[.!?]\s+|,\s+')

    def chunk(self, text: str) -> List[str]:
        """
        텍스트를 절 단위로 분리

        Args:
            text: 입력 텍스트

        Returns:
            절 단위로 분리된 문자열 리스트
        """
        if not text or not text.strip():
            return []

        text = text.strip()

        # 1단계: 접속사 기준 분리
        chunks = self._split_by_conjunctions(text)

        # 2단계: 연결어미 기준 분리
        result = []
        for chunk in chunks:
            sub_chunks = self._split_by_connectives(chunk)
            result.extend(sub_chunks)

        # 3단계: 문장부호 기준 분리 (선택적)
        if self.use_punctuation:
            final_result = []
            for chunk in result:
                sub_chunks = self._split_by_punctuation(chunk)
                final_result.extend(sub_chunks)
            result = final_result

        # 4단계: 필터링 (최소 길이, 공백 제거)
        result = [
            chunk.strip()
            for chunk in result
            if chunk.strip() and len(chunk.strip()) >= self.min_chunk_length
        ]

        # 청크가 없으면 원본 반환
        if not result:
            return [text] if len(text) >= self.min_chunk_length else []

        return result

    def _split_by_conjunctions(self, text: str) -> List[str]:
        """접속사 기준 분리"""
        if self.keep_delimiter:
            # 접속사를 유지하면서 분리
            parts = self._conjunction_regex.split(text)
            delimiters = self._conjunction_regex.findall(text)

            result = []
            for i, part in enumerate(parts):
                if part.strip():
                    result.append(part.strip())
                if i < len(delimiters) and self.keep_delimiter:
                    # 다음 청크 앞에 접속사 추가
                    pass  # 접속사는 버림 (의미 단위 분리이므로)
            return result if result else [text]
        else:
            return [p.strip() for p in self._conjunction_regex.split(text) if p.strip()]

    def _split_by_connectives(self, text: str) -> List[str]:
        """연결어미 기준 분리"""
        # 연결어미 위치 찾기
        matches = list(self._connective_regex.finditer(text))

        if not matches:
            return [text]

        result = []
        last_end = 0

        for match in matches:
            # 연결어미까지 포함한 청크
            chunk = text[last_end:match.end()].strip()
            if chunk:
                result.append(chunk)
            last_end = match.end()

        # 마지막 부분
        if last_end < len(text):
            remaining = text[last_end:].strip()
            if remaining:
                result.append(remaining)

        return result if result else [text]

    def _split_by_punctuation(self, text: str) -> List[str]:
        """문장부호 기준 분리"""
        parts = self._punctuation_regex.split(text)
        return [p.strip() for p in parts if p.strip()]

    def chunk_batch(self, texts: List[str]) -> List[List[str]]:
        """
        배치 청킹

        Args:
            texts: 텍스트 리스트

        Returns:
            각 텍스트별 청크 리스트
        """
        return [self.chunk(text) for text in texts]

    def chunk_with_metadata(self, text: str) -> List[dict]:
        """
        메타데이터와 함께 청킹

        Returns:
            [{'text': '청크내용', 'index': 0, 'start': 0, 'end': 10}, ...]
        """
        chunks = self.chunk(text)
        result = []
        current_pos = 0

        for i, chunk in enumerate(chunks):
            # 원본에서 청크 위치 찾기
            start = text.find(chunk, current_pos)
            if start == -1:
                start = current_pos
            end = start + len(chunk)

            result.append({
                'text': chunk,
                'index': i,
                'start': start,
                'end': end
            })
            current_pos = end

        return result
