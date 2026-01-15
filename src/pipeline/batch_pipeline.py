"""
배치 파이프라인 (리팩토링된 모듈 통합)

9단계 리뷰 분석 파이프라인:
[1] 리뷰 로드
[2] 빈 리뷰 제거 (5자 미만)
[3] 블라인드/삭제 제거 + 30개 이하 지점 삭제
[4] 2단계 감정 분석 (Lexicon → BERT)
[5] 긍정 리뷰 필터링 (score >= 0.45)
[6] 리뷰당 키워드 추출 (명사 + 형용사)
[7] 지점별 키워드 집계 (가중치 적용)
[8] AI 요약 생성
[9] 결과 저장
"""
import os
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional

from ..config.settings import get_settings
from ..config.stopwords import LexiconConfig
from ..analysis.sentiment import HybridSentimentAnalyzer
from ..analysis.keywords import KeywordExtractor, KeywordAggregator, WeightCalculator
from ..llm import OpenAIProvider, GeminiProvider, PromptTemplates, validate_summary


class BatchPipeline:
    """
    배치 리뷰 분석 파이프라인

    의존성 주입 패턴으로 각 모듈을 조합하여 사용합니다.
    """

    def __init__(
        self,
        sentiment_analyzer: HybridSentimentAnalyzer = None,
        keyword_extractor: KeywordExtractor = None,
        keyword_aggregator: KeywordAggregator = None,
        llm_provider=None,
        min_reviews: int = 30,
        min_review_length: int = 5,
        sentiment_threshold: float = 0.45,
        use_parallel: bool = True,
        n_jobs: int = -1
    ):
        """
        Args:
            sentiment_analyzer: 감정분석기 (기본값: HybridSentimentAnalyzer)
            keyword_extractor: 키워드 추출기 (기본값: KeywordExtractor)
            keyword_aggregator: 키워드 집계기 (기본값: KeywordAggregator)
            llm_provider: LLM Provider (기본값: 설정에 따름)
            min_reviews: 지점당 최소 리뷰 수
            min_review_length: 최소 리뷰 길이
            sentiment_threshold: 긍정 판정 임계값
            use_parallel: 병렬 처리 사용 여부
            n_jobs: 병렬 작업 수 (-1: 모든 CPU)
        """
        settings = get_settings()

        self.sentiment_analyzer = sentiment_analyzer or HybridSentimentAnalyzer(
            use_bert=settings.use_bert,
            confident_high=settings.lexicon_confident_high,
            confident_low=settings.lexicon_confident_low
        )
        self.keyword_extractor = keyword_extractor or KeywordExtractor()
        self.keyword_aggregator = keyword_aggregator or KeywordAggregator()

        # LLM Provider 설정
        if llm_provider:
            self.llm_provider = llm_provider
        elif settings.llm_provider == 'openai':
            self.llm_provider = OpenAIProvider(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                rpm=settings.openai_rpm
            )
        elif settings.llm_provider == 'gemini':
            self.llm_provider = GeminiProvider(
                api_key=settings.gemini_api_key,
                model=settings.gemini_model,
                rpm=settings.gemini_rpm
            )
        else:
            self.llm_provider = None

        self.min_reviews = min_reviews
        self.min_review_length = min_review_length
        self.sentiment_threshold = sentiment_threshold
        self.use_parallel = use_parallel
        self.n_jobs = n_jobs

        # 부정 패턴
        self.negative_patterns = LexiconConfig.NEGATIVE_PATTERNS

        # 통계
        self.stats = {}

    def run(self, input_file: str, output_dir: str = 'output') -> Dict:
        """
        전체 파이프라인 실행

        Args:
            input_file: 입력 엑셀 파일 경로
            output_dir: 출력 디렉토리

        Returns:
            실행 통계
        """
        start = datetime.now()

        print("\n" + "="*60)
        print("🚀 리뷰 요약 파이프라인 v4.0 시작 (모듈화 버전)")
        print("="*60)

        # Step 1: 데이터 로드
        df = self._load_data(input_file)

        # Step 2: 빈 리뷰 제거
        df = self._remove_empty_reviews(df)

        # Step 3: 블라인드/삭제 제거 + 지점 필터링
        df = self._filter_reviews(df)

        # Step 4: 감정 분석
        df = self._analyze_sentiment(df)

        # Step 5: 긍정 리뷰 필터링
        df_positive = self._filter_positive(df)

        # Step 6: 키워드 추출
        df_positive = self._extract_keywords(df_positive)

        # Step 7: 지점별 키워드 집계
        keywords_df = self._aggregate_keywords(df_positive)

        # Step 8: AI 요약 생성 + 결과 저장
        os.makedirs(output_dir, exist_ok=True)
        results = self._generate_summaries(keywords_df, df_positive, output_dir)

        # 완료
        elapsed = (datetime.now() - start).total_seconds()
        self.stats['elapsed_seconds'] = elapsed

        print("\n" + "="*60)
        print(f"✅ 파이프라인 완료! (소요 시간: {elapsed:.1f}초)")
        print("="*60)

        return self.stats

    def _load_data(self, file_path: str) -> pd.DataFrame:
        """Step 1: 데이터 로드"""
        print("\n" + "="*60)
        print("[Step 1] 데이터 로드")
        print("="*60)

        df = pd.read_excel(file_path)
        self.stats['total_reviews'] = len(df)
        print(f"✅ {len(df):,}개 리뷰 로드 완료")
        return df

    def _remove_empty_reviews(self, df: pd.DataFrame) -> pd.DataFrame:
        """Step 2: 빈 리뷰 제거"""
        print("\n" + "="*60)
        print("[Step 2] 빈 리뷰 제거")
        print("="*60)

        before = len(df)

        # null 제거
        df = df.dropna(subset=['리뷰내용'])

        # 빈 문자열 제거
        df = df[df['리뷰내용'].str.strip() != '']

        # 최소 길이 미만 제거
        df = df[df['리뷰내용'].str.len() >= self.min_review_length]

        after = len(df)
        self.stats['empty_removed'] = before - after
        print(f"✅ {before - after:,}개 제거 → {after:,}개 남음")
        return df

    def _filter_reviews(self, df: pd.DataFrame) -> pd.DataFrame:
        """Step 3: 블라인드/삭제 제거 + 지점 필터링"""
        print("\n" + "="*60)
        print("[Step 3] 블라인드/삭제 제거 + 지점 필터링")
        print("="*60)

        before = len(df)

        # 블라인드/삭제 상태 제거
        if '상태' in df.columns:
            df = df[~df['상태'].isin(['블라인드', '삭제', 'blind', 'deleted'])]

        # 최소 리뷰 수 이하 지점 제거
        branch_counts = df['지점번호'].value_counts()
        valid_branches = branch_counts[branch_counts >= self.min_reviews].index
        df = df[df['지점번호'].isin(valid_branches)]

        after = len(df)
        self.stats['filtered_reviews'] = after
        self.stats['branch_count'] = len(df['지점번호'].unique())
        print(f"✅ {before - after:,}개 제거 → {after:,}개 ({self.stats['branch_count']}개 지점)")
        return df

    def _analyze_sentiment(self, df: pd.DataFrame) -> pd.DataFrame:
        """Step 4: 감정 분석"""
        print("\n" + "="*60)
        print("[Step 4] 2단계 하이브리드 감정 분석")
        print("="*60)
        print(f"   1차: Lexicon (빠름) → 2차: BERT (애매한 경우만)")

        df = df.copy()
        texts = df['리뷰내용'].astype(str).tolist()

        # 병렬 처리
        if self.use_parallel:
            results = self.sentiment_analyzer.analyze_batch_parallel(
                texts, n_jobs=self.n_jobs, verbose=0
            )
        else:
            results = self.sentiment_analyzer.analyze_batch(texts)

        df['sentiment'] = [r.sentiment for r in results]
        df['sentiment_score'] = [r.score for r in results]

        # 통계
        sentiment_counts = df['sentiment'].value_counts()
        self.stats['sentiment'] = {
            'positive': int(sentiment_counts.get('positive', 0)),
            'neutral': int(sentiment_counts.get('neutral', 0)),
            'negative': int(sentiment_counts.get('negative', 0))
        }

        stats = self.sentiment_analyzer.get_stats()
        total = len(df)
        print(f"\n✅ 감정 분석 완료")
        print(f"   - 긍정: {self.stats['sentiment']['positive']:,}개 ({self.stats['sentiment']['positive']/total*100:.1f}%)")
        print(f"   - 중립: {self.stats['sentiment']['neutral']:,}개 ({self.stats['sentiment']['neutral']/total*100:.1f}%)")
        print(f"   - 부정: {self.stats['sentiment']['negative']:,}개 ({self.stats['sentiment']['negative']/total*100:.1f}%)")
        print(f"   - BERT 호출: {stats.get('bert_used', 0):,}회")

        return df

    def _filter_positive(self, df: pd.DataFrame) -> pd.DataFrame:
        """Step 5: 감정분석 통계 (필터링 없음 - 모든 리뷰 유지)"""
        print("\n" + "="*60)
        print("[Step 5] 감정분석 통계 (필터링 없음)")
        print("="*60)

        # 모든 리뷰 유지 (필터링 없음)
        df_filtered = df.copy()

        positive_count = len(df_filtered[df_filtered['sentiment'] == 'positive'])
        negative_count = len(df_filtered[df_filtered['sentiment'] == 'negative'])
        neutral_count = len(df_filtered[df_filtered['sentiment'] == 'neutral'])

        self.stats['positive_reviews'] = positive_count
        self.stats['negative_reviews'] = negative_count
        self.stats['neutral_reviews'] = neutral_count
        print(f"✅ {len(df_filtered):,}개 리뷰 (필터링 없음)")
        print(f"   - 긍정: {positive_count:,}개 ({positive_count/len(df_filtered)*100:.1f}%)")
        print(f"   - 부정: {negative_count:,}개 ({negative_count/len(df_filtered)*100:.1f}%)")
        print(f"   - 중립: {neutral_count:,}개 ({neutral_count/len(df_filtered)*100:.1f}%)")
        return df_filtered

    def _extract_keywords(self, df: pd.DataFrame) -> pd.DataFrame:
        """Step 6: 키워드 추출"""
        print("\n" + "="*60)
        print("[Step 6] 키워드 추출 (MeCab)")
        print("="*60)

        texts = df['리뷰내용'].astype(str).tolist()

        # 병렬 처리
        if self.use_parallel:
            keywords_list = self.keyword_extractor.extract_batch_parallel(
                texts, n_jobs=self.n_jobs, verbose=0
            )
        else:
            keywords_list = self.keyword_extractor.extract_batch(texts)

        df['keywords'] = keywords_list

        # 부정 리뷰 키워드 제거
        df['is_negative'] = df['리뷰내용'].apply(
            lambda x: any(p in str(x) for p in self.negative_patterns)
        )
        df.loc[df['is_negative'], 'keywords'] = df.loc[df['is_negative'], 'keywords'].apply(lambda x: [])

        total_keywords = sum(len(kw) for kw in df['keywords'])
        self.stats['total_keywords'] = total_keywords
        print(f"✅ 총 {total_keywords:,}개 키워드 추출")
        return df

    def _aggregate_keywords(self, df: pd.DataFrame) -> pd.DataFrame:
        """Step 7: 지점별 키워드 집계"""
        print("\n" + "="*60)
        print("[Step 7] 지점별 키워드 집계 (가중치 적용)")
        print("="*60)

        keywords_df = self.keyword_aggregator.aggregate(df)
        print(f"✅ {len(keywords_df)}개 지점 키워드 집계 완료")
        return keywords_df

    def _generate_summaries(
        self,
        keywords_df: pd.DataFrame,
        reviews_df: pd.DataFrame,
        output_dir: str
    ) -> Dict:
        """Step 8: AI 요약 생성 + 결과 저장"""
        print("\n" + "="*60)
        print("[Step 8] AI 요약 생성")
        print("="*60)

        summary_rows = []
        total = len(keywords_df)

        for i, (_, row) in enumerate(keywords_df.iterrows(), 1):
            if i % 50 == 0:
                print(f"   {i}/{total} 처리 중...")

            branch_id = row['branch_id']
            keywords = row['keywords']
            review_count = row['review_count']

            # 지점명 가져오기 (reviews_df에서)
            branch_name = None
            if '지점명' in reviews_df.columns:
                branch_rows = reviews_df[reviews_df['지점번호'] == branch_id]['지점명']
                if not branch_rows.empty:
                    branch_name = str(branch_rows.iloc[0])

            # 대표 리뷰 추출
            representative_reviews = self._get_representative_reviews(
                reviews_df, branch_id, keywords[:10]
            )

            # AI 요약 생성 (v2: 지점명 전달)
            summary = self._generate_summary(
                keywords, review_count, representative_reviews, branch_name
            )

            summary_rows.append({
                '지점번호': branch_id,
                '리뷰수': review_count,
                'TOP3키워드': ', '.join(keywords[:3]),
                'AI요약': summary
            })

        # 엑셀 저장
        summary_path = os.path.join(output_dir, 'branch_summaries.xlsx')
        pd.DataFrame(summary_rows).to_excel(summary_path, index=False)
        print(f"✅ {summary_path}")

        # 키워드 엑셀 저장
        keywords_path = self.keyword_aggregator.export_to_excel(
            keywords_df,
            os.path.join(output_dir, 'branch_keywords.xlsx')
        )
        print(f"✅ {keywords_path}")

        # Supabase용 데이터
        supabase_data = []
        for row in summary_rows:
            keywords = row['TOP3키워드'].split(', ') if row['TOP3키워드'] else []
            supabase_data.append({
                'branch_id': row['지점번호'],
                'ai_summary': row['AI요약'],
                'keywords': keywords,
                'review_count': row['리뷰수']
            })

        self.stats['summaries_generated'] = len(summary_rows)
        return {
            'summary_path': summary_path,
            'keywords_path': keywords_path,
            'supabase_data': supabase_data
        }

    def _get_representative_reviews(
        self,
        df: pd.DataFrame,
        branch_id: int,
        keywords: List[str]
    ) -> List[str]:
        """지점별 대표 리뷰 추출 (긍정 3개 + 부정 2개 = 5개)"""
        branch_df = df[df['지점번호'] == branch_id].copy()

        if branch_df.empty:
            return []

        def count_keywords(text):
            if not isinstance(text, str):
                return 0
            return sum(1 for kw in keywords if kw in text)

        branch_df['kw_count'] = branch_df['리뷰내용'].apply(count_keywords)

        # 긍정 리뷰 3개 선택
        positive_df = branch_df[branch_df['sentiment'] == 'positive']
        positive_reviews = positive_df.nlargest(3, 'kw_count')['리뷰내용'].tolist() if not positive_df.empty else []

        # 부정 리뷰 2개 선택
        negative_df = branch_df[branch_df['sentiment'] == 'negative']
        negative_reviews = negative_df.nlargest(2, 'kw_count')['리뷰내용'].tolist() if not negative_df.empty else []

        # 합치기 (긍정 먼저, 부정 나중)
        all_reviews = positive_reviews + negative_reviews

        return [str(r)[:100] for r in all_reviews if r]

    def _generate_summary(
        self,
        keywords: List[str],
        review_count: int,
        representative_reviews: List[str],
        branch_name: str = None
    ) -> str:
        """
        LLM으로 요약 생성 (v2: 지점 유형별 프롬프트 + 검증)

        Args:
            keywords: 키워드 리스트
            review_count: 리뷰 수
            representative_reviews: 대표 리뷰 리스트
            branch_name: 지점명 (유형 판별용)
        """
        if not keywords:
            return PromptTemplates.get_default_summary(keywords)

        # LLM Provider 미설정
        if not self.llm_provider or not self.llm_provider.is_available():
            return PromptTemplates.get_default_summary(keywords)

        # 프롬프트 생성 (v2: 지점명 전달)
        system_prompt, user_prompt = PromptTemplates.build_summary_prompt(
            keywords=keywords,
            review_count=review_count,
            representative_reviews=representative_reviews,
            branch_name=branch_name
        )

        # 요약 생성 (temperature 0.5로 낮춰 일관성 향상)
        response = self.llm_provider.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=300,
            temperature=0.5
        )

        if response.success:
            summary = response.content

            # 검증
            is_valid, errors = validate_summary(summary)
            if not is_valid:
                print(f"   ⚠️ [{branch_name or '지점'}] 검증 경고: {'; '.join(errors)}")

            return summary

        return PromptTemplates.get_default_summary(keywords)
