"""
배치 파이프라인 v5.0 (감정분석 제거)

4단계 리뷰 분석 파이프라인:
[1] 데이터 로드
[2] 키워드 추출 (청킹 + MeCab)
[3] 태그+감정 분류 (임베딩 기반) + AI 요약 생성
[4] Supabase 저장

변경사항 (v5.0):
- 리뷰별 감정분석(Lexicon+BERT) 제거
- 키워드별 감정 판단으로 대체 (임베딩 분류기)
- 파이프라인 속도 대폭 개선

구현 일지:
- 2026-01-19: v5.0 - 감정분석 단계 제거, 키워드 감정으로 대체
- 2026-01-19: v4.0 - 필터링 단계 제거, 9단계→5단계 간소화
- 2026-01-16: Container 연동, DTO 지원 추가
"""
import os
import re
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Pattern, TYPE_CHECKING

from core.config import get_settings
from core.stopwords import LexiconConfig

from analysis import KeywordExtractor, KeywordAggregator, WeightCalculator
from services.llm import OpenAIProvider, SummaryPromptBuilder, validate_summary

# 기간별 요약 설정
PERIOD_CONFIGS = {
    '1m': {'days': 30, 'label': '1개월'},
    '3m': {'days': 90, 'label': '3개월'},
    '6m': {'days': 180, 'label': '6개월'},
    '1y': {'days': 365, 'label': '1년'},
    'all': {'days': None, 'label': '전체'}
}

# 타입 별칭
LLMProvider = Union[OpenAIProvider]

# 순환 참조 방지를 위한 TYPE_CHECKING
if TYPE_CHECKING:
    from schemas.dto import PipelineConfigDTO, PipelineResultDTO


class BatchPipeline:
    """
    배치 리뷰 분석 파이프라인

    의존성 주입 패턴으로 각 모듈을 조합하여 사용합니다.
    
    사용법:
        # 방법 1: 직접 생성
        pipeline = BatchPipeline(sentiment_analyzer=..., llm_provider=...)
        
        # 방법 2: 직접 설정
        pipeline = BatchPipeline(min_reviews=30)
        result = pipeline.run("data/reviews.xlsx")
    """
    
    @classmethod
    def from_container(cls, container: 'Container') -> 'BatchPipeline':
        """
        Container로부터 파이프라인 생성 (팩토리 메서드)

        Args:
            container: DI Container 인스턴스

        Returns:
            BatchPipeline 인스턴스
        """
        config = container.config
        return cls(
            keyword_extractor=container.keyword_extractor,
            keyword_aggregator=container.keyword_aggregator,
            llm_provider=container.llm_provider,
            min_reviews=config.min_reviews,
            min_review_length=config.min_review_length,
            sentiment_threshold=config.sentiment_threshold,
            use_parallel=config.use_parallel,
            n_jobs=config.n_jobs
        )

    def __init__(
        self,
        keyword_extractor: Optional[KeywordExtractor] = None,
        keyword_aggregator: Optional[KeywordAggregator] = None,
        llm_provider: Optional[LLMProvider] = None,
        min_reviews: int = 30,
        min_review_length: int = 5,
        sentiment_threshold: float = 0.45,
        use_parallel: bool = True,
        n_jobs: int = -1,
        use_chunking: bool = False,
        use_embedding_tags: bool = False,
        use_hybrid_absa: bool = False
    ) -> None:
        """
        Args:
            keyword_extractor: 키워드 추출기 (기본값: KeywordExtractor)
            keyword_aggregator: 키워드 집계기 (기본값: KeywordAggregator)
            llm_provider: LLM Provider (기본값: 설정에 따름)
            min_reviews: 지점당 최소 리뷰 수
            min_review_length: 최소 리뷰 길이
            sentiment_threshold: 긍정 판정 임계값
            use_parallel: 병렬 처리 사용 여부
            n_jobs: 병렬 작업 수 (-1: 모든 CPU)
            use_chunking: 절 단위 청킹 사용 여부
            use_embedding_tags: 임베딩 기반 태그 분류 사용 여부
            use_hybrid_absa: 하이브리드 ABSA 분류 사용 여부 (권장)
        """
        settings = get_settings()

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
        else:
            self.llm_provider = None

        self.min_reviews = min_reviews
        self.min_review_length = min_review_length
        self.sentiment_threshold = sentiment_threshold
        self.use_parallel = use_parallel
        self.n_jobs = n_jobs
        self.use_chunking = use_chunking
        self.use_embedding_tags = use_embedding_tags
        self.use_hybrid_absa = use_hybrid_absa

        # 청킹 모듈 (지연 로딩)
        self._chunker = None

        # 임베딩 태그 분류기 (지연 로딩)
        self._embedding_classifier = None

        # 하이브리드 분류기 (지연 로딩)
        self._hybrid_classifier = None

        # 지점별 태그+감정 데이터 캐시
        self._branch_tag_sentiment_cache: Dict[int, Dict[str, Dict[str, List[str]]]] = {}

        # 부정 패턴 (정규표현식 컴파일로 성능 최적화)
        self.negative_patterns = LexiconConfig.NEGATIVE_PATTERNS
        self._negative_pattern_regex = re.compile(
            '|'.join(map(re.escape, self.negative_patterns))
        ) if self.negative_patterns else None

        # 통계
        self.stats = {}

    def run(self, input_file: str, output_dir: str = 'output', generate_period_summaries: bool = True) -> Dict:
        """
        전체 파이프라인 실행

        Args:
            input_file: 입력 엑셀 파일 경로
            output_dir: 출력 디렉토리
            generate_period_summaries: 기간별 요약 생성 여부 (기본 True)

        Returns:
            실행 통계
        """
        start = datetime.now()

        print("\n" + "="*60)
        print("🚀 리뷰 요약 파이프라인 v5.0 시작 (감정분석 제거)")
        print("="*60)

        # Step 1: 데이터 로드
        df = self._load_data(input_file)

        # 지점 통계 계산
        branch_counts = df.groupby('지점번호').size()
        self.stats['valid_branches'] = len(branch_counts)
        self.stats['filtered_reviews'] = len(df)
        self.stats['branch_count'] = len(branch_counts)
        print(f"   → {len(branch_counts)}개 지점, {len(df):,}개 리뷰")

        # Step 2: 키워드 추출
        df = self._extract_keywords(df)

        # Step 3: 태그+감정 분류 + 키워드 집계 + AI 요약 생성
        if self.use_embedding_tags:
            self._classify_tags_for_summary(df)
        keywords_df = self._aggregate_keywords(df)
        os.makedirs(output_dir, exist_ok=True)

        if generate_period_summaries:
            results = self._generate_summaries_by_period(keywords_df, df, output_dir)
        else:
            results = self._generate_summaries(keywords_df, df, output_dir)

        # Step 4: 태그 매핑 및 집계 (DB 저장)
        self._aggregate_tags(df)

        # 완료
        elapsed = (datetime.now() - start).total_seconds()
        self.stats['elapsed_seconds'] = elapsed

        print("\n" + "="*60)
        print(f"✅ 파이프라인 완료! (소요 시간: {elapsed:.1f}초)")
        print("="*60)

        return self.stats

    def run_with_result(self, input_file: str, output_dir: str = 'output') -> 'PipelineResultDTO':
        """
        전체 파이프라인 실행 (PipelineResultDTO 반환)

        run() 메서드와 동일하지만 구조화된 DTO를 반환합니다.

        Args:
            input_file: 입력 엑셀 파일 경로
            output_dir: 출력 디렉토리

        Returns:
            PipelineResultDTO: 실행 결과 DTO
        """
        from schemas.dto import PipelineResultDTO

        started_at = datetime.now()

        try:
            stats = self.run(input_file, output_dir)

            return PipelineResultDTO(
                success=True,
                total_reviews=stats.get('total_reviews', 0),
                processed_reviews=stats.get('filtered_reviews', 0),
                total_branches=stats.get('branch_count', 0),
                summaries_generated=stats.get('summaries_generated', 0),
                total_duration_seconds=stats.get('elapsed_seconds', 0),
                started_at=started_at,
                finished_at=datetime.now()
            )

        except Exception as e:
            return PipelineResultDTO(
                success=False,
                total_reviews=self.stats.get('total_reviews', 0),
                processed_reviews=0,
                total_branches=0,
                summaries_generated=0,
                error_message=str(e),
                started_at=started_at,
                finished_at=datetime.now()
            )

    def _load_data(self, file_path: str) -> pd.DataFrame:
        """Step 1: 데이터 로드"""
        print("\n" + "="*60)
        print("[Step 1] 데이터 로드")
        print("="*60)

        # 파일 존재 여부 확인
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {file_path}")

        try:
            df = pd.read_excel(file_path)
        except Exception as e:
            raise ValueError(f"엑셀 파일 로드 실패: {file_path}\n원인: {e}")

        # 필수 컬럼 확인
        required_columns = ['리뷰내용', '지점번호']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"필수 컬럼 누락: {missing_columns}")

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





    def _extract_keywords(self, df: pd.DataFrame) -> pd.DataFrame:
        """Step 2: 키워드 추출 (청킹 옵션 지원)"""
        print("\n" + "="*60)
        if self.use_chunking:
            print("[Step 2] 키워드 추출 (청킹 + MeCab)")
        else:
            print("[Step 2] 키워드 추출 (MeCab)")
        print("="*60)

        texts = df['리뷰내용'].astype(str).tolist()

        # 청킹 사용 시
        if self.use_chunking:
            if self._chunker is None:
                from analysis import ClauseChunker
                self._chunker = ClauseChunker()
                print("   → 절 단위 청킹 활성화")

            # 청킹 + 키워드 추출
            results = self.keyword_extractor.extract_batch_with_chunking(
                texts, chunker=self._chunker
            )
            # flat_keywords만 사용 (중복 제거된 전체 키워드)
            keywords_list = [r['flat_keywords'] for r in results]

            # 청킹 통계
            total_chunks = sum(len(r['chunks']) for r in results)
            print(f"   → 총 {total_chunks:,}개 청크 생성")
        else:
            # 기존 방식: 병렬 처리
            if self.use_parallel:
                keywords_list = self.keyword_extractor.extract_batch_parallel(
                    texts, n_jobs=self.n_jobs, verbose=0
                )
            else:
                keywords_list = self.keyword_extractor.extract_batch(texts)

        df['keywords'] = keywords_list

        # 부정 리뷰 키워드 제거 (정규표현식으로 최적화)
        if self._negative_pattern_regex:
            df['is_negative'] = df['리뷰내용'].astype(str).str.contains(
                self._negative_pattern_regex, na=False
            )
            # pandas 호환성: apply로 빈 리스트 할당
            df['keywords'] = df.apply(
                lambda row: [] if row.get('is_negative', False) else row['keywords'],
                axis=1
            )

        total_keywords = sum(len(kw) for kw in df['keywords'])
        self.stats['total_keywords'] = total_keywords
        print(f"✅ 총 {total_keywords:,}개 키워드 추출")
        return df

    def _aggregate_keywords(self, df: pd.DataFrame) -> pd.DataFrame:
        """Step 3: 지점별 키워드 집계"""
        print("\n" + "="*60)
        print("[Step 3] 지점별 키워드 집계 (가중치 적용)")
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
        print("[Step 3] AI 요약 생성")
        print("="*60)

        summary_rows = []
        total = len(keywords_df)

        # 지점명 캐시 생성 (O(1) 조회)
        branch_name_cache: Dict[int, str] = {}
        if '지점명' in reviews_df.columns:
            branch_name_cache = (
                reviews_df.groupby('지점번호')['지점명']
                .first()
                .to_dict()
            )

        for i, (_, row) in enumerate(keywords_df.iterrows(), 1):
            if i % 50 == 0:
                print(f"   {i}/{total} 처리 중...")

            branch_id = row['branch_id']
            keywords = row['keywords']
            review_count = row['review_count']

            # 지점명 가져오기 (캐시에서 O(1) 조회)
            branch_name = branch_name_cache.get(branch_id)

            # 대표 리뷰 추출
            representative_reviews = self._get_representative_reviews(
                reviews_df, branch_id, keywords[:10]
            )

            # 도움돼요수 상위 리뷰 추출
            top_helpful_reviews = self._extract_top_helpful_reviews(
                reviews_df, branch_id
            )

            # AI 요약 생성 (v4: 태그+감정 정보 활용)
            branch_df = reviews_df[reviews_df['지점번호'] == branch_id]
            summary = self._generate_summary(
                keywords, review_count, representative_reviews, branch_name, branch_id,
                top_helpful_reviews=top_helpful_reviews,
                branch_df=branch_df
            )

            # 태그 그룹 추출 (긍정 키워드가 많은 순)
            top_tags = self._get_top_tags_for_branch(branch_id)

            summary_rows.append({
                '지점번호': branch_id,
                '리뷰수': review_count,
                'TOP3태그': top_tags[:3],
                'AI요약': summary
            })

        # DB 저장만 수행 (엑셀 출력 제거)

        # Supabase용 데이터
        supabase_data = []
        for row in summary_rows:
            supabase_data.append({
                'branch_id': row['지점번호'],
                'ai_summary': row['AI요약'],
                'keywords': row['TOP3태그'],  # 태그 그룹 저장
                'review_count': row['리뷰수']
            })

        # DB 저장
        self._save_summaries_to_db(supabase_data)

        self.stats['summaries_generated'] = len(summary_rows)
        return {
            'supabase_data': supabase_data
        }

    def _save_summaries_to_db(self, summaries: List[Dict]):
        """요약을 DB에 저장 (branch_summaries 테이블 - 통합)"""
        try:
            import sys
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'app'))
            from supabase_client import upsert_branch_summary
        except ImportError:
            print(f"   ⚠️ DB 저장 스킵 (supabase_client 임포트 실패)")
            return

        saved = 0
        for summary in summaries:
            branch_id = summary['branch_id']
            keywords = summary.get('keywords', [])

            try:
                upsert_branch_summary({
                    'branch_id': branch_id,
                    'review_count': summary['review_count'],
                    'keyword_1': keywords[0] if len(keywords) > 0 else None,
                    'keyword_2': keywords[1] if len(keywords) > 1 else None,
                    'keyword_3': keywords[2] if len(keywords) > 2 else None,
                    'summary_all': summary['ai_summary'],
                    'status': 'draft'
                })
                saved += 1
            except Exception as e:
                print(f"   ⚠️ DB 저장 오류 (지점 {branch_id}): {e}")

        print(f"   💾 {saved}/{len(summaries)}개 저장 완료")

    def _get_representative_reviews(
        self,
        df: pd.DataFrame,
        branch_id: int,
        keywords: List[str]
    ) -> List[str]:
        """지점별 대표 리뷰 추출 (키워드 포함 많은 순 5개)"""
        branch_df = df[df['지점번호'] == branch_id].copy()

        if branch_df.empty:
            return []

        def count_keywords(text):
            if not isinstance(text, str):
                return 0
            return sum(1 for kw in keywords if kw in text)

        branch_df['kw_count'] = branch_df['리뷰내용'].apply(count_keywords)

        # 키워드가 많이 포함된 리뷰 5개 선택
        top_reviews = branch_df.nlargest(5, 'kw_count')['리뷰내용'].tolist()

        return [str(r)[:100] for r in top_reviews if r]

    def _extract_top_helpful_reviews(
        self,
        df: pd.DataFrame,
        branch_id: int,
        top_n: int = 10
    ) -> Optional[List[Dict]]:
        """
        도움돼요수 상위 리뷰 추출

        Args:
            df: 전체 리뷰 데이터프레임
            branch_id: 지점 ID
            top_n: 추출할 리뷰 수

        Returns:
            [{'review': '...', 'helpful_count': 14, 'tags': '고객응대(+),...'}, ...]
        """
        if df is None or df.empty:
            return None

        # 지점별 필터링
        branch_df = df[df['지점번호'] == branch_id].copy()

        if branch_df.empty or '도움돼요수' not in branch_df.columns:
            return None

        # 도움돼요수 상위 추출
        top_helpful_df = branch_df.nlargest(top_n, '도움돼요수')
        result = []

        for _, row in top_helpful_df.iterrows():
            helpful_count = int(row.get('도움돼요수', 0))
            if helpful_count >= 1:
                result.append({
                    'review': str(row.get('리뷰내용', ''))[:200],
                    'helpful_count': helpful_count,
                    'tags': str(row.get('태그별감정', '')) if '태그별감정' in row else ''
                })

        # 최소 3개 이상이어야 의미 있음
        return result if len(result) >= 3 else None

    def _calculate_sentiment_stats(
        self,
        branch_df: pd.DataFrame,
        tag_sentiment_data: dict
    ) -> Optional[Dict]:
        """
        감정 통계 계산 (평점 기반 우선, 없으면 키워드 기반)

        평점 기준:
        - 긍정: 3~5점 (평균)
        - 부정: 1~2점 (평균)

        Args:
            branch_df: 지점별 리뷰 데이터프레임
            tag_sentiment_data: 태그별 감정 데이터 (폴백용)

        Returns:
            {'positive_count': N, 'negative_count': N, 'positive_ratio': N, 'negative_ratio': N}
        """
        # 1. 평점 기반 계산 시도
        if branch_df is not None and not branch_df.empty:
            rating_cols = ['지점평점(친절/편의성)', '차량평점', '인수/반납편의성']
            available_cols = [col for col in rating_cols if col in branch_df.columns]

            if available_cols:
                # 평균 평점 계산
                branch_df = branch_df.copy()
                branch_df['avg_rating'] = branch_df[available_cols].mean(axis=1)

                # 긍정(3~5점) / 부정(1~2점) 분류
                positive_count = int((branch_df['avg_rating'] >= 3).sum())
                negative_count = int((branch_df['avg_rating'] < 3).sum())
                total = positive_count + negative_count

                if total > 0:
                    return {
                        'positive_count': positive_count,
                        'negative_count': negative_count,
                        'positive_ratio': positive_count / total * 100,
                        'negative_ratio': negative_count / total * 100
                    }

        # 2. 폴백: 키워드 기반 계산
        if tag_sentiment_data:
            positive_count = sum(len(v.get('positive', [])) for v in tag_sentiment_data.values())
            negative_count = sum(len(v.get('negative', [])) for v in tag_sentiment_data.values())
            total = positive_count + negative_count

            if total > 0:
                return {
                    'positive_count': positive_count,
                    'negative_count': negative_count,
                    'positive_ratio': positive_count / total * 100,
                    'negative_ratio': negative_count / total * 100
                }

        return None

    def _generate_summary(
        self,
        keywords: List[str],
        review_count: int,
        representative_reviews: List[str],
        branch_name: str = None,
        branch_id: int = None,
        max_retries: int = 2,
        top_helpful_reviews: Optional[List[Dict]] = None,
        branch_df: pd.DataFrame = None
    ) -> str:
        """
        LLM으로 요약 생성 (v4: 태그+감정 정보 활용)

        Args:
            keywords: 키워드 리스트
            review_count: 리뷰 수
            representative_reviews: 대표 리뷰 리스트
            branch_name: 지점명 (유형 판별용)
            branch_id: 지점 ID (태그 데이터 조회용)
            max_retries: 검증 실패 시 최대 재시도 횟수
            top_helpful_reviews: 도움돼요수 상위 리뷰 (태그 정보 포함)
            branch_df: 지점별 리뷰 데이터프레임 (평점 기반 통계용)
        """
        if not keywords:
            return SummaryPromptBuilder.get_default_summary(keywords)

        # LLM Provider 미설정
        if not self.llm_provider or not self.llm_provider.is_available():
            return SummaryPromptBuilder.get_default_summary(keywords)

        # 프롬프트 생성
        system_prompt, user_prompt = SummaryPromptBuilder.create_summary_prompt(
            keywords=keywords,
            review_count=review_count,
            representative_reviews=representative_reviews,
            branch_name=branch_name
        )

        last_summary = None
        last_errors = []

        for attempt in range(max_retries + 1):
            # 재시도 시 temperature 낮춤
            temperature = 0.5 if attempt == 0 else 0.3

            response = self.llm_provider.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=300,
                temperature=temperature
            )

            if not response.success:
                continue

            summary = response.content
            last_summary = summary

            # 검증
            is_valid, errors = validate_summary(summary)
            if is_valid:
                return summary

            last_errors = errors
            if attempt < max_retries:
                continue  # 재시도

        # 모든 재시도 실패 시 마지막 요약 반환 (경고와 함께)
        if last_summary:
            print(f"   ⚠️ [{branch_name or '지점'}] 검증 경고 (재시도 {max_retries}회 후): {'; '.join(last_errors)}")
            return last_summary

        return SummaryPromptBuilder.get_default_summary(keywords)

    # =========================================================================
    # 기간별 요약 생성 (Step 8 확장)
    # =========================================================================

    def _filter_by_period(self, df: pd.DataFrame, period_type: str) -> pd.DataFrame:
        """
        기간별 데이터 필터링

        Args:
            df: 전체 데이터프레임
            period_type: 기간 타입 ('all', '1m', '3m', '6m', '1y')

        Returns:
            필터링된 데이터프레임
        """
        if period_type == 'all':
            return df

        config = PERIOD_CONFIGS.get(period_type)
        if not config or not config.get('days'):
            return df

        days = config['days']
        cutoff_date = datetime.now() - timedelta(days=days)

        # 날짜 컬럼 확인 (등록일시, 리뷰일자, created_at 등)
        date_columns = ['등록일시', '리뷰일자', 'created_at', 'review_date']
        date_col = None

        for col in date_columns:
            if col in df.columns:
                date_col = col
                break

        if not date_col:
            print(f"   ⚠️ 날짜 컬럼을 찾을 수 없어 전체 데이터 사용")
            return df

        # 날짜 타입 변환
        df_copy = df.copy()
        df_copy[date_col] = pd.to_datetime(df_copy[date_col], errors='coerce')

        # 필터링
        filtered = df_copy[df_copy[date_col] >= cutoff_date]

        print(f"   {period_type} ({config['label']}): {len(filtered):,}개 리뷰 (전체 {len(df):,}개)")

        return filtered

    def _generate_summaries_by_period(
        self,
        keywords_df: pd.DataFrame,
        reviews_df: pd.DataFrame,
        output_dir: str
    ) -> Dict:
        """
        기간별 요약 생성 (5개 기간)

        Args:
            keywords_df: 지점별 키워드 집계
            reviews_df: 리뷰 원본 데이터
            output_dir: 출력 디렉토리

        Returns:
            기간별 결과 딕셔너리
        """
        print("\n" + "="*60)
        print("[Step 3] 기간별 AI 요약 생성")
        print("="*60)

        all_results = {}

        for period_type, config in PERIOD_CONFIGS.items():
            print(f"\n=== {config['label']} 요약 생성 ({period_type}) ===")

            # 기간별 데이터 필터링
            period_df = self._filter_by_period(reviews_df, period_type)

            if period_df.empty:
                print(f"   {period_type}: 데이터 없음, 스킵")
                continue

            # 기간별 키워드 재집계
            period_keywords_df = self.keyword_aggregator.aggregate(period_df)

            # 요약 생성
            results = self._generate_summaries_for_period(
                period_keywords_df,
                period_df,
                output_dir,
                period_type
            )

            all_results[period_type] = results

        self.stats['period_summaries'] = {
            period: len(results.get('supabase_data', []))
            for period, results in all_results.items()
        }

        return all_results

    def _generate_summaries_for_period(
        self,
        keywords_df: pd.DataFrame,
        reviews_df: pd.DataFrame,
        output_dir: str,
        period_type: str
    ) -> Dict:
        """특정 기간의 요약 생성"""
        summary_rows = []
        total = len(keywords_df)

        # 지점명 캐시 생성
        branch_name_cache: Dict[int, str] = {}
        if '지점명' in reviews_df.columns:
            branch_name_cache = (
                reviews_df.groupby('지점번호')['지점명']
                .first()
                .to_dict()
            )

        for i, (_, row) in enumerate(keywords_df.iterrows(), 1):
            if i % 50 == 0:
                print(f"   {i}/{total} 처리 중...")

            branch_id = row['branch_id']
            keywords = row['keywords']
            review_count = row['review_count']

            # 지점명 가져오기
            branch_name = branch_name_cache.get(branch_id)

            # 대표 리뷰 추출
            representative_reviews = self._get_representative_reviews(
                reviews_df, branch_id, keywords[:10]
            )

            # 도움돼요수 상위 리뷰 추출
            top_helpful_reviews = self._extract_top_helpful_reviews(
                reviews_df, branch_id
            )

            # 해당 지점 데이터 필터링 (평점 기반 통계용)
            branch_df = reviews_df[reviews_df['지점번호'] == branch_id]

            # AI 요약 생성 (v4: 태그+감정 정보 활용)
            summary = self._generate_summary(
                keywords, review_count, representative_reviews, branch_name, branch_id,
                top_helpful_reviews=top_helpful_reviews,
                branch_df=branch_df
            )

            # 태그 그룹 추출 (긍정 키워드가 많은 순)
            top_tags = self._get_top_tags_for_branch(branch_id)

            summary_rows.append({
                '지점번호': branch_id,
                '리뷰수': review_count,
                'TOP3태그': top_tags[:3],
                'AI요약': summary
            })

        # DB 저장만 수행 (엑셀 출력 제거)

        # Supabase 저장
        supabase_data = []
        for row in summary_rows:
            supabase_data.append({
                'branch_id': row['지점번호'],
                'ai_summary': row['AI요약'],
                'keywords': row['TOP3태그'],  # 태그 그룹 저장
                'review_count': row['리뷰수'],
                'period_type': period_type
            })

        # DB 저장 (upsert_summary_with_period 사용)
        self._save_period_summaries_to_db(supabase_data, period_type)

        return {
            'supabase_data': supabase_data
        }

    def _save_period_summaries_to_db(self, summaries: List[Dict], period_type: str):
        """기간별 요약을 DB에 저장"""
        try:
            import sys
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'app'))
            from supabase_client import upsert_summary_with_period
        except ImportError:
            print(f"   ⚠️ DB 저장 스킵 (supabase_client 임포트 실패)")
            return

        saved = 0
        for summary in summaries:
            try:
                upsert_summary_with_period(
                    branch_id=summary['branch_id'],
                    period_type=period_type,
                    ai_summary=summary['ai_summary'],
                    keywords=summary['keywords'],
                    review_count=summary['review_count']
                )
                saved += 1
            except Exception as e:
                print(f"   ⚠️ DB 저장 오류 (지점 {summary['branch_id']}): {e}")

        print(f"   💾 {period_type} 요약 {saved}/{len(summaries)}개 DB 저장")

    # =========================================================================
    # 태그 분류 (요약용) - Step 3
    # =========================================================================

    def _classify_tags_for_summary(self, df: pd.DataFrame):
        """
        요약 생성을 위한 태그+감정 분류 (캐시 저장)

        Args:
            df: 키워드가 추출된 데이터프레임
        """
        print("\n" + "="*60)
        if self.use_hybrid_absa:
            print("[Step 3] 태그+감정 분류 (하이브리드 ABSA)")
        else:
            print("[Step 3] 태그+감정 분류 (요약용)")
        print("="*60)

        # 하이브리드 ABSA 사용 시
        if self.use_hybrid_absa:
            self._classify_tags_with_hybrid(df)
            return

        # 기존 임베딩 분류기 사용
        if self._embedding_classifier is None:
            try:
                from analysis import EmbeddingTagClassifier
                self._embedding_classifier = EmbeddingTagClassifier(lazy_load=True)
                print("   → 임베딩 기반 태그 분류기 로딩")
            except ImportError as e:
                print(f"   ⚠️ 임베딩 분류기 로드 실패: {e}")
                return

        # 지점별 키워드 수집
        branch_keywords: Dict[int, List[str]] = {}

        for _, row in df.iterrows():
            branch_id = row.get('지점번호')
            keywords = row.get('keywords', [])

            if not branch_id or not keywords:
                continue

            if branch_id not in branch_keywords:
                branch_keywords[branch_id] = []

            branch_keywords[branch_id].extend(keywords)

        print(f"   → {len(branch_keywords)}개 지점의 키워드 수집")

        # 전체 고유 키워드 수집
        all_unique_keywords = set()
        for kw_list in branch_keywords.values():
            all_unique_keywords.update(kw_list)

        all_unique_keywords = list(all_unique_keywords)
        print(f"   → 고유 키워드 {len(all_unique_keywords):,}개")

        # 배치 분류
        print("   → 임베딩 기반 태그+감정 분류 중...")
        classifications = self._embedding_classifier.classify_batch_with_sentiment(all_unique_keywords)

        # 키워드 → (태그, 점수, 감정) 매핑
        keyword_classification: Dict[str, tuple] = {}
        for kw, (tag, score, sentiment) in zip(all_unique_keywords, classifications):
            keyword_classification[kw] = (tag, score, sentiment)

        # 지점별 태그+감정 데이터 구성
        for branch_id, keywords in branch_keywords.items():
            tag_sentiment: Dict[str, Dict[str, List[str]]] = {}

            for kw in keywords:
                if kw not in keyword_classification:
                    continue

                tag, score, sentiment = keyword_classification[kw]

                if tag not in tag_sentiment:
                    tag_sentiment[tag] = {'positive': [], 'negative': [], 'neutral': []}

                # 중복 제거하여 추가
                if kw not in tag_sentiment[tag][sentiment]:
                    tag_sentiment[tag][sentiment].append(kw)

            self._branch_tag_sentiment_cache[branch_id] = tag_sentiment

        # 통계
        total_positive = sum(
            len(ts.get('positive', []))
            for ts_data in self._branch_tag_sentiment_cache.values()
            for ts in ts_data.values()
        )
        total_negative = sum(
            len(ts.get('negative', []))
            for ts_data in self._branch_tag_sentiment_cache.values()
            for ts in ts_data.values()
        )
        total_neutral = sum(
            len(ts.get('neutral', []))
            for ts_data in self._branch_tag_sentiment_cache.values()
            for ts in ts_data.values()
        )

        print(f"   ✅ 태그+감정 분류 완료")
        print(f"   📊 긍정: {total_positive:,}개 / 부정: {total_negative:,}개 / 중립: {total_neutral:,}개")

    def _classify_tags_with_hybrid(self, df: pd.DataFrame):
        """
        하이브리드 ABSA를 사용한 태그+감정 분류

        리뷰 전체 텍스트를 ABSA로 분석하여 혼합 감정 처리 개선
        """
        # 하이브리드 분류기 초기화
        if self._hybrid_classifier is None:
            try:
                from analysis import HybridClassifier
                self._hybrid_classifier = HybridClassifier(lazy_load=True)
                print("   → 하이브리드 ABSA 분류기 로딩")
            except ImportError as e:
                print(f"   ⚠️ 하이브리드 분류기 로드 실패: {e}")
                return

        # 지점별 리뷰+키워드 수집
        branch_data: Dict[int, List[dict]] = {}

        for _, row in df.iterrows():
            branch_id = row.get('지점번호')
            review = str(row.get('리뷰내용', ''))
            keywords = row.get('keywords', [])

            if not branch_id or not review:
                continue

            if branch_id not in branch_data:
                branch_data[branch_id] = []

            branch_data[branch_id].append({
                'review': review,
                'keywords': keywords
            })

        print(f"   → {len(branch_data)}개 지점의 리뷰 수집")

        total_reviews = sum(len(reviews) for reviews in branch_data.values())
        print(f"   → 총 {total_reviews:,}개 리뷰 분석 중...")

        processed = 0
        # 지점별 분류
        for branch_id, reviews in branch_data.items():
            tag_sentiment: Dict[str, Dict[str, List[str]]] = {}

            for item in reviews:
                # 하이브리드 분류 (리뷰 + 키워드)
                result = self._hybrid_classifier.classify_review(
                    review=item['review'],
                    keywords=item['keywords']
                )

                # 결과 병합
                for tag, sentiments in result.items():
                    if tag not in tag_sentiment:
                        tag_sentiment[tag] = {'positive': [], 'negative': [], 'neutral': []}

                    for sentiment_type in ['positive', 'negative', 'neutral']:
                        for kw in sentiments.get(sentiment_type, []):
                            if kw not in tag_sentiment[tag][sentiment_type]:
                                tag_sentiment[tag][sentiment_type].append(kw)

                processed += 1
                if processed % 500 == 0:
                    print(f"   {processed:,}/{total_reviews:,} 처리 중...")

            self._branch_tag_sentiment_cache[branch_id] = tag_sentiment

        # 통계
        total_positive = sum(
            len(ts.get('positive', []))
            for ts_data in self._branch_tag_sentiment_cache.values()
            for ts in ts_data.values()
        )
        total_negative = sum(
            len(ts.get('negative', []))
            for ts_data in self._branch_tag_sentiment_cache.values()
            for ts in ts_data.values()
        )
        total_neutral = sum(
            len(ts.get('neutral', []))
            for ts_data in self._branch_tag_sentiment_cache.values()
            for ts in ts_data.values()
        )

        print(f"   ✅ 하이브리드 ABSA 분류 완료")
        print(f"   📊 긍정: {total_positive:,}개 / 부정: {total_negative:,}개 / 중립: {total_neutral:,}개")

    def _get_tag_sentiment_for_branch(self, branch_id: int) -> Dict[str, Dict[str, List[str]]]:
        """
        지점별 태그+감정 데이터 반환

        Args:
            branch_id: 지점 ID

        Returns:
            태그별 감정 데이터 딕셔너리
        """
        return self._branch_tag_sentiment_cache.get(branch_id, {})

    def _get_top_tags_for_branch(self, branch_id: int, top_n: int = 5) -> List[str]:
        """
        지점별 상위 태그 그룹 반환 (긍정 키워드가 많은 순)

        Args:
            branch_id: 지점 ID
            top_n: 반환할 태그 수

        Returns:
            태그 그룹명 리스트
        """
        tag_data = self._branch_tag_sentiment_cache.get(branch_id, {})

        if not tag_data:
            return []

        # 긍정 키워드 수 기준 정렬
        tag_scores = []
        for tag_name, sentiments in tag_data.items():
            if tag_name == '기타':
                continue  # '기타' 태그 제외
            positive_count = len(sentiments.get('positive', []))
            if positive_count > 0:
                tag_scores.append((tag_name, positive_count))

        # 긍정 키워드 많은 순 정렬
        tag_scores.sort(key=lambda x: x[1], reverse=True)

        return [tag for tag, _ in tag_scores[:top_n]]

    # =========================================================================
    # 태그 매핑 및 집계 (Step 4)
    # =========================================================================

    def _aggregate_tags(self, df: pd.DataFrame):
        """
        태그 매핑 및 지점별 집계 (임베딩 기반 분류 지원)

        Args:
            df: 키워드가 추출된 데이터프레임
        """
        print("\n" + "="*60)
        if self.use_embedding_tags:
            print("[Step 4] 태그 매핑 및 집계 (임베딩 기반)")
        else:
            print("[Step 4] 태그 매핑 및 집계 (규칙 기반)")
        print("="*60)

        try:
            from analysis import TagMapper
            import sys
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'app'))
            from supabase_client import (
                get_or_create_tag,
                create_keyword_mapping,
                upsert_branch_tags,
                get_all_categories
            )
        except ImportError as e:
            print(f"   ⚠️ 태그 집계 스킵 (모듈 임포트 실패): {e}")
            return

        # 임베딩 분류기 초기화 (use_embedding_tags=True 시)
        if self.use_embedding_tags:
            if self._embedding_classifier is None:
                try:
                    from analysis import EmbeddingTagClassifier
                    self._embedding_classifier = EmbeddingTagClassifier(lazy_load=True)
                    print("   → 임베딩 기반 태그 분류기 활성화")
                except ImportError as e:
                    print(f"   ⚠️ 임베딩 분류기 로드 실패, 규칙 기반으로 폴백: {e}")
                    self.use_embedding_tags = False

        mapper = TagMapper()

        # 카테고리 ID 캐시
        try:
            categories = get_all_categories()
            category_id_map = {c['name']: c['id'] for c in categories}
        except Exception:
            category_id_map = {}

        # 지점별 키워드 수집
        branch_keywords: Dict[int, Dict[str, int]] = {}

        for _, row in df.iterrows():
            branch_id = row.get('지점번호')
            keywords = row.get('keywords', [])

            if not branch_id or not keywords:
                continue

            if branch_id not in branch_keywords:
                branch_keywords[branch_id] = {}

            for kw in keywords:
                branch_keywords[branch_id][kw] = branch_keywords[branch_id].get(kw, 0) + 1

        print(f"   {len(branch_keywords)}개 지점의 키워드 수집 완료")

        # 전체 고유 키워드 수집 (임베딩 배치 처리용)
        all_unique_keywords = set()
        for kw_counts in branch_keywords.values():
            all_unique_keywords.update(kw_counts.keys())

        all_unique_keywords = list(all_unique_keywords)
        print(f"   → 고유 키워드 {len(all_unique_keywords):,}개")

        # 키워드 → 태그 그룹 + 감정 매핑
        keyword_tag_map: Dict[str, tuple] = {}  # {키워드: (태그그룹명, 점수, 감정)}

        if self.use_embedding_tags and self._embedding_classifier:
            # 임베딩 기반 배치 분류 + 감정 판단
            print("   → 임베딩 기반 태그 + 감정 분류 중...")
            classifications = self._embedding_classifier.classify_batch_with_sentiment(all_unique_keywords)
            for kw, (tag_group, score, sentiment) in zip(all_unique_keywords, classifications):
                keyword_tag_map[kw] = (tag_group, score, sentiment)
            print(f"   → {len(keyword_tag_map):,}개 키워드 분류 완료")
        else:
            # 규칙 기반 매핑
            for kw in all_unique_keywords:
                tag_name, sentiment = mapper.map_keyword_to_tag(kw)
                category = mapper.get_category_for_tag(tag_name)
                keyword_tag_map[kw] = (category or '기타', 1.0, sentiment)

        # 태그 저장
        tag_cache: Dict[str, int] = {}  # 태그명 → 태그 ID
        mapped_count = 0
        positive_count = 0
        negative_count = 0

        for branch_id, kw_counts in branch_keywords.items():
            branch_tags = []

            for keyword, count in kw_counts.items():
                tag_group, score, sentiment = keyword_tag_map.get(keyword, ('기타', 0.0, 'positive'))

                # 태그 이름 결정
                if self.use_embedding_tags:
                    tag_name = tag_group
                else:
                    tag_name, _ = mapper.map_keyword_to_tag(keyword)

                # 감정 통계 (neutral은 별도 처리하지 않음)
                if sentiment == 'positive':
                    positive_count += count
                elif sentiment == 'negative':
                    negative_count += count
                # neutral은 통계에서 제외

                # 태그 ID 조회 (캐시 우선)
                if tag_name not in tag_cache:
                    category_name = tag_group if self.use_embedding_tags else mapper.get_category_for_tag(tag_name)
                    category_id = category_id_map.get(category_name)

                    try:
                        tag = get_or_create_tag(tag_name, category_id, sentiment)
                        if tag and tag.get('id'):
                            tag_cache[tag_name] = tag['id']

                            # 키워드 매핑 저장
                            create_keyword_mapping(keyword, tag['id'], is_auto=True)
                    except Exception:
                        continue

                tag_id = tag_cache.get(tag_name)
                if tag_id:
                    # 임베딩 점수를 가중치에 반영
                    weighted_score = count * score if self.use_embedding_tags else count * 1.0
                    branch_tags.append({
                        'tag_id': tag_id,
                        'count': count,
                        'weighted_score': weighted_score
                    })
                    mapped_count += 1

            # 지점별 태그 저장 (전체 기간)
            if branch_tags:
                try:
                    upsert_branch_tags(branch_id, 'all', branch_tags)
                except Exception:
                    pass

        print(f"   ✅ 태그 매핑 완료: {mapped_count}개 키워드 → {len(tag_cache)}개 태그")
        print(f"   📊 감정 분포: 긍정 {positive_count:,}개 / 부정 {negative_count:,}개")
