"""
하이브리드 감정분석 (Lexicon + BERT)

병렬 처리 지원 (joblib)
"""
from typing import List, Tuple, Optional
from .base import SentimentAnalyzer, SentimentResult
from .lexicon import LexiconAnalyzer
from .bert import BertAnalyzer


class HybridSentimentAnalyzer(SentimentAnalyzer):
    """
    2단계 하이브리드 감정분석기

    1차: Lexicon (빠름) - 확실한 경우 바로 결정 (score >= 0.7 또는 <= 0.3)
    2차: BERT (정밀) - 애매한 경우만 처리 (0.3 < score < 0.7)

    이 방식으로 대부분의 리뷰를 빠르게 처리하면서도
    애매한 경우에는 정밀한 분석을 수행합니다.
    """

    def __init__(
        self,
        lexicon_analyzer: LexiconAnalyzer = None,
        bert_analyzer: BertAnalyzer = None,
        use_bert: bool = True,
        confident_high: float = 0.7,
        confident_low: float = 0.3
    ):
        """
        Args:
            lexicon_analyzer: Lexicon 분석기 (기본값: 새로 생성)
            bert_analyzer: BERT 분석기 (기본값: 새로 생성)
            use_bert: BERT 사용 여부
            confident_high: 확실한 긍정 임계값
            confident_low: 확실한 부정 임계값
        """
        self.lexicon = lexicon_analyzer or LexiconAnalyzer(
            confident_high=confident_high,
            confident_low=confident_low
        )
        self.bert = bert_analyzer or BertAnalyzer()
        self.use_bert = use_bert
        self.confident_high = confident_high
        self.confident_low = confident_low

        # 통계
        self.stats = {
            'total': 0,
            'lexicon_only': 0,
            'bert_used': 0
        }

    def analyze(self, text: str) -> SentimentResult:
        """
        2단계 하이브리드 감정 분석

        Args:
            text: 분석할 텍스트

        Returns:
            SentimentResult: 감정분석 결과
        """
        self.stats['total'] += 1

        # 빈 텍스트
        if not text or not text.strip():
            return SentimentResult(
                sentiment='neutral',
                score=0.5,
                method='hybrid'
            )

        # 1차: Lexicon 기반 빠른 분류
        lexicon_score = self.lexicon.calculate_score(text)

        # 확실한 긍정 (score >= 0.7)
        if lexicon_score >= self.confident_high:
            self.stats['lexicon_only'] += 1
            return SentimentResult(
                sentiment='positive',
                score=round(lexicon_score, 3),
                method='lexicon'
            )

        # 확실한 부정 (score <= 0.3)
        if lexicon_score <= self.confident_low:
            self.stats['lexicon_only'] += 1
            return SentimentResult(
                sentiment='negative',
                score=round(lexicon_score, 3),
                method='lexicon'
            )

        # 2차: 애매한 구간 (0.3 < score < 0.7) → BERT로 정밀 분석
        if self.use_bert and self.bert.is_available:
            self.stats['bert_used'] += 1
            return self.bert.analyze(text)

        # BERT 사용 불가 시 Lexicon으로 결정
        self.stats['lexicon_only'] += 1
        if lexicon_score >= 0.5:
            sentiment = 'neutral'
        else:
            sentiment = 'negative'

        return SentimentResult(
            sentiment=sentiment,
            score=round(lexicon_score, 3),
            method='lexicon'
        )

    def analyze_with_detail(self, text: str) -> Tuple[SentimentResult, bool]:
        """
        감정 분석 + BERT 사용 여부 반환

        Args:
            text: 분석할 텍스트

        Returns:
            tuple: (SentimentResult, used_bert)
        """
        result = self.analyze(text)
        used_bert = result.method == 'bert'
        return result, used_bert

    def analyze_batch(self, texts: List[str]) -> List[SentimentResult]:
        """
        배치 감정 분석

        Args:
            texts: 분석할 텍스트 리스트

        Returns:
            list[SentimentResult]: 감정분석 결과 리스트
        """
        return [self.analyze(text) for text in texts]

    def analyze_batch_parallel(
        self,
        texts: List[str],
        n_jobs: int = -1,
        batch_size: int = 1000,
        verbose: int = 0
    ) -> List[SentimentResult]:
        """
        병렬 배치 감정 분석 (joblib 사용)

        Lexicon 분석은 병렬로, BERT는 순차 처리 (GPU 공유 문제 방지)

        Args:
            texts: 분석할 텍스트 리스트
            n_jobs: 병렬 작업 수 (-1: 모든 CPU)
            batch_size: 배치 크기
            verbose: 상세 출력 레벨

        Returns:
            list[SentimentResult]: 감정분석 결과 리스트
        """
        try:
            from joblib import Parallel, delayed
        except ImportError:
            print("⚠️ joblib 미설치 - 순차 처리 사용")
            return self.analyze_batch(texts)

        total = len(texts)

        # 1단계: Lexicon 분석 병렬 처리
        lexicon_results = Parallel(n_jobs=n_jobs, verbose=verbose)(
            delayed(self._analyze_lexicon_only)(text) for text in texts
        )

        # 2단계: BERT 필요한 경우만 수집
        results = []
        bert_indices = []
        bert_texts = []

        for i, (text, lex_result) in enumerate(zip(texts, lexicon_results)):
            if lex_result is not None:
                # Lexicon으로 확정
                results.append(lex_result)
            else:
                # BERT 필요
                results.append(None)
                bert_indices.append(i)
                bert_texts.append(text)

        # 3단계: BERT 분석 (순차 처리 - GPU 공유 문제 방지)
        if bert_texts and self.use_bert and self.bert.is_available:
            bert_results = self.bert.analyze_batch(bert_texts)
            for idx, bert_result in zip(bert_indices, bert_results):
                results[idx] = bert_result
                self.stats['bert_used'] += 1

        # BERT 미사용 시 Lexicon 결과로 대체
        for i, result in enumerate(results):
            if result is None:
                score = self.lexicon.calculate_score(texts[i])
                sentiment = 'neutral' if score >= 0.5 else 'negative'
                results[i] = SentimentResult(
                    sentiment=sentiment,
                    score=round(score, 3),
                    method='lexicon'
                )
                self.stats['lexicon_only'] += 1

        self.stats['total'] += total
        return results

    def _analyze_lexicon_only(self, text: str) -> Optional[SentimentResult]:
        """
        Lexicon만으로 분석 (병렬 처리용)

        Returns:
            SentimentResult: 확정된 경우, None: BERT 필요
        """
        if not text or not text.strip():
            return SentimentResult(
                sentiment='neutral',
                score=0.5,
                method='lexicon'
            )

        score = self.lexicon.calculate_score(text)

        if score >= self.confident_high:
            return SentimentResult(
                sentiment='positive',
                score=round(score, 3),
                method='lexicon'
            )

        if score <= self.confident_low:
            return SentimentResult(
                sentiment='negative',
                score=round(score, 3),
                method='lexicon'
            )

        # BERT 필요
        return None

    def get_stats(self) -> dict:
        """분석 통계 반환"""
        total = self.stats['total']
        if total == 0:
            return self.stats

        return {
            **self.stats,
            'lexicon_ratio': round(self.stats['lexicon_only'] / total * 100, 1),
            'bert_ratio': round(self.stats['bert_used'] / total * 100, 1)
        }

    def reset_stats(self):
        """통계 초기화"""
        self.stats = {
            'total': 0,
            'lexicon_only': 0,
            'bert_used': 0
        }
