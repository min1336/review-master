"""
통합 파이프라인 모듈

BasePipeline: 공통 기능 (키워드 추출, 전처리, 감정 분석)
BatchPipeline: Excel 배치 처리
IncrementalPipeline: API 증분 처리
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

# .env 로드
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except ImportError:
    pass

from core.config import get_settings
from core.stopwords import LexiconConfig
from infrastructure.llm import OpenAIProvider

from ..analysis import KeywordAggregator, KeywordExtractor

# 순환 참조 방지
if TYPE_CHECKING:
    from schemas.dto import PipelineResultDTO

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pipeline")

# 기간별 요약 설정
PERIOD_CONFIGS = {
    "1m": {"days": 30, "label": "1개월"},
    "3m": {"days": 90, "label": "3개월"},
    "6m": {"days": 180, "label": "6개월"},
    "1y": {"days": 365, "label": "1년"},
    "all": {"days": None, "label": "전체"},
}

# 타입 별칭
LLMProvider = OpenAIProvider


# =============================================================================
# BasePipeline: 공통 기능
# =============================================================================


class BasePipeline(ABC):
    """
    파이프라인 공통 기능 베이스 클래스

    공통 기능:
    - MeCab 키워드 추출
    - 전처리/필터링 (욕설, 광고, 빈 리뷰)
    - 감정 분석 (Lexicon 기반)
    - Supabase 연동
    """

    def __init__(self):
        self.mecab = None
        self.supabase_client = None
        self.stats = {}

        self._init_mecab()
        self._init_supabase()

    def _init_mecab(self):
        """MeCab 초기화"""
        try:
            import mecab

            self.mecab = mecab.MeCab()
            logger.info("MeCab 초기화 완료")
        except ImportError:
            logger.warning("MeCab 미설치 - 정규식 폴백 사용")

    def _init_supabase(self):
        """Supabase 클라이언트 초기화"""
        try:
            from supabase_client import get_client

            self.supabase_client = get_client()
            logger.info("Supabase 연결 완료")
        except Exception as e:
            logger.warning(f"Supabase 연결 실패: {e}")

    # =========================================================================
    # 키워드 추출
    # =========================================================================

    def extract_keywords(self, text: str) -> list[str]:
        """
        텍스트에서 키워드 추출 (MeCab 우선, 정규식 폴백)

        Args:
            text: 분석할 텍스트

        Returns:
            키워드 리스트
        """
        if not text:
            return []

        if self.mecab:
            try:
                keywords = []
                for token in self.mecab.parse(text):
                    pos = token.pos
                    word = token.surface
                    # 명사(NNG, NNP) + 형용사(VA)
                    is_target_pos = (
                        pos.startswith("NNG")
                        or pos.startswith("NNP")
                        or pos.startswith("VA")
                    )
                    is_valid = len(word) >= 2 and word not in LexiconConfig.STOP_WORDS
                    if is_target_pos and is_valid:
                        keywords.append(word)
                return keywords
            except Exception:
                pass

        # 정규식 폴백
        words = re.findall(r"[가-힣]{2,}", text)
        return [w for w in words if w not in LexiconConfig.STOP_WORDS]

    # =========================================================================
    # 전처리/필터링
    # =========================================================================

    def preprocess_review(self, review: dict) -> dict | None:
        """
        리뷰 전처리 (필터링)

        Args:
            review: 리뷰 딕셔너리

        Returns:
            통과한 리뷰 또는 None (필터됨)
        """
        text = review.get("리뷰내용", "") or review.get("content", "")

        # 1. 빈 리뷰 필터
        if not text or len(text.strip()) < 5:
            return None

        # 2. 욕설/비방 필터
        text_lower = text.lower()
        for pattern in LexiconConfig.PROFANITY_PATTERNS:
            if pattern in text_lower:
                logger.debug(f"욕설 필터: {text[:30]}...")
                return None

        # 3. 광고 필터
        for pattern in LexiconConfig.AD_PATTERNS:
            if pattern in text_lower:
                logger.debug(f"광고 필터: {text[:30]}...")
                return None

        # 4. 블라인드/삭제 필터
        status = review.get("리뷰상태", "") or review.get("status", "")
        if status in ["블라인드", "삭제", "blind", "deleted"]:
            return None

        return review

    # =========================================================================
    # 감정 분석
    # =========================================================================

    def analyze_sentiment(
        self, text: str, keywords: list[str] = None
    ) -> tuple[str, float]:
        """
        감정 분석 (HybridClassifier 기반)

        Args:
            text: 분석할 텍스트
            keywords: 추출된 키워드 리스트 (선택)

        Returns:
            (sentiment, score) - ('positive'/'neutral'/'negative', 0~1)
        """
        if not text:
            return "neutral", 0.5

        # HybridClassifier 지연 로딩
        if not hasattr(self, "_hybrid_classifier") or self._hybrid_classifier is None:
            from ..analysis import HybridClassifier

            self._hybrid_classifier = HybridClassifier(lazy_load=True)

        result = self._hybrid_classifier.get_review_summary(text, keywords)
        overall = result.get("overall_sentiment", "neutral")

        # 점수 계산
        pos_count = len(result.get("positive_aspects", []))
        neg_count = len(result.get("negative_aspects", []))
        total = pos_count + neg_count

        if total == 0:
            return "neutral", 0.5

        score = (pos_count + 1) / (total + 2)  # Laplace smoothing

        return overall, score

    def is_valid_sentiment(self, review: dict) -> tuple[bool, float, str]:
        """
        리뷰 감정 분석 (긍정/부정 포함, 중립 제외)

        Args:
            review: 리뷰 딕셔너리

        Returns:
            (is_valid, score, sentiment)
        """
        text = review.get("리뷰내용", "") or review.get("content", "")
        sentiment, score = self.analyze_sentiment(text)
        is_valid = sentiment in ["positive", "negative"]
        return is_valid, score, sentiment

    # =========================================================================
    # 추상 메서드
    # =========================================================================

    @abstractmethod
    def run(self, *args, **kwargs) -> dict:
        """파이프라인 실행"""
        pass


# =============================================================================
# BatchPipeline: Excel 배치 처리
# =============================================================================


class BatchPipeline(BasePipeline):
    """
    배치 리뷰 분석 파이프라인

    Excel 파일을 읽어 전체 지점의 리뷰를 분석하고 AI 요약을 생성합니다.

    사용법:
        pipeline = BatchPipeline(min_reviews=30)
        result = pipeline.run("data/reviews.xlsx")
    """

    @classmethod
    def from_container(cls, container) -> BatchPipeline:
        """Container로부터 파이프라인 생성 (팩토리 메서드)"""
        config = container.config
        return cls(
            keyword_extractor=container.keyword_extractor,
            keyword_aggregator=container.keyword_aggregator,
            llm_provider=container.llm_provider,
            min_reviews=config.min_reviews,
            min_review_length=config.min_review_length,
            sentiment_threshold=config.sentiment_threshold,
            use_parallel=config.use_parallel,
            n_jobs=config.n_jobs,
        )

    def __init__(
        self,
        keyword_extractor: KeywordExtractor | None = None,
        keyword_aggregator: KeywordAggregator | None = None,
        llm_provider: LLMProvider | None = None,
        min_reviews: int = 30,
        min_review_length: int = 5,
        sentiment_threshold: float = 0.45,
        use_parallel: bool = True,
        n_jobs: int = -1,
        use_chunking: bool = False,
    ) -> None:
        """
        Args:
            keyword_extractor: 키워드 추출기
            keyword_aggregator: 키워드 집계기
            llm_provider: LLM Provider
            min_reviews: 지점당 최소 리뷰 수
            min_review_length: 최소 리뷰 길이
            sentiment_threshold: 긍정 판정 임계값
            use_parallel: 병렬 처리 사용 여부
            n_jobs: 병렬 작업 수 (-1: 모든 CPU)
            use_chunking: 절 단위 청킹 사용 여부
        """
        super().__init__()

        settings = get_settings()

        self.keyword_extractor = keyword_extractor or KeywordExtractor()
        self.keyword_aggregator = keyword_aggregator or KeywordAggregator()

        # LLM Provider 설정
        if llm_provider:
            self.llm_provider = llm_provider
        elif settings.llm_provider == "openai":
            self.llm_provider = OpenAIProvider(
                api_key=settings.openai_api_key.get_secret_value(),
                model=settings.openai_model,
                rpm=settings.openai_rpm,
            )
        else:
            self.llm_provider = None

        self.min_reviews = min_reviews
        self.min_review_length = min_review_length
        self.sentiment_threshold = sentiment_threshold
        self.use_parallel = use_parallel
        self.n_jobs = n_jobs
        self.use_chunking = use_chunking

        # 청킹 모듈 (지연 로딩)
        self._chunker = None

        # 하이브리드 분류기 (지연 로딩)
        self._hybrid_classifier = None

        # 지점별 태그+감정 데이터 캐시
        self._branch_tag_sentiment_cache: dict[
            int, dict[str, dict[str, list[str]]]
        ] = {}

        # 부정 패턴 (정규표현식 컴파일로 성능 최적화)
        self.negative_patterns = LexiconConfig.NEGATIVE_PATTERNS
        self._negative_pattern_regex = (
            re.compile("|".join(map(re.escape, self.negative_patterns)))
            if self.negative_patterns
            else None
        )

    def run(
        self,
        input_file: str,
        output_dir: str = "output",
        generate_period_summaries: bool = True,
    ) -> dict:
        """
        전체 파이프라인 실행

        Args:
            input_file: 입력 엑셀 파일 경로
            output_dir: 출력 디렉토리
            generate_period_summaries: 기간별 요약 생성 여부

        Returns:
            실행 통계
        """
        start = datetime.now()

        print("\n" + "=" * 60)
        print("🚀 리뷰 요약 파이프라인 v5.0 시작 (감정분석 제거)")
        print("=" * 60)

        # Step 1: 데이터 로드
        df = self._load_data(input_file)

        # 지점 통계 계산
        branch_counts = df.groupby("지점번호").size()
        self.stats["valid_branches"] = len(branch_counts)
        self.stats["filtered_reviews"] = len(df)
        self.stats["branch_count"] = len(branch_counts)
        print(f"   → {len(branch_counts)}개 지점, {len(df):,}개 리뷰")

        # Step 2: 키워드 추출
        df = self._extract_keywords_batch(df)

        # Step 3: 태그+감정 분류 + 키워드 집계 + AI 요약 생성
        self._classify_tags_for_summary(df)
        keywords_df = self._aggregate_keywords(df)
        os.makedirs(output_dir, exist_ok=True)

        if generate_period_summaries:
            self._generate_summaries_by_period(keywords_df, df, output_dir)
        else:
            self._generate_summaries(keywords_df, df, output_dir)

        # Step 4: 태그 매핑 및 집계 (DB 저장)
        self._aggregate_tags(df)

        # 완료
        elapsed = (datetime.now() - start).total_seconds()
        self.stats["elapsed_seconds"] = elapsed

        print("\n" + "=" * 60)
        print(f"✅ 파이프라인 완료! (소요 시간: {elapsed:.1f}초)")
        print("=" * 60)

        return self.stats

    def run_with_result(
        self, input_file: str, output_dir: str = "output"
    ) -> PipelineResultDTO:
        """전체 파이프라인 실행 (PipelineResultDTO 반환)"""
        from schemas.dto import PipelineResultDTO

        started_at = datetime.now()

        try:
            stats = self.run(input_file, output_dir)

            return PipelineResultDTO(
                success=True,
                total_reviews=stats.get("total_reviews", 0),
                processed_reviews=stats.get("filtered_reviews", 0),
                total_branches=stats.get("branch_count", 0),
                summaries_generated=stats.get("summaries_generated", 0),
                total_duration_seconds=stats.get("elapsed_seconds", 0),
                started_at=started_at,
                finished_at=datetime.now(),
            )

        except Exception as e:
            return PipelineResultDTO(
                success=False,
                total_reviews=self.stats.get("total_reviews", 0),
                processed_reviews=0,
                total_branches=0,
                summaries_generated=0,
                error_message=str(e),
                started_at=started_at,
                finished_at=datetime.now(),
            )

    def _load_data(self, file_path: str) -> pd.DataFrame:
        """Step 1: 데이터 로드"""
        print("\n" + "=" * 60)
        print("[Step 1] 데이터 로드")
        print("=" * 60)

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {file_path}")

        try:
            df = pd.read_excel(file_path)
        except Exception as e:
            raise ValueError(f"엑셀 파일 로드 실패: {file_path}\n원인: {e}") from e

        required_columns = ["리뷰내용", "지점번호"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"필수 컬럼 누락: {missing_columns}")

        self.stats["total_reviews"] = len(df)
        print(f"✅ {len(df):,}개 리뷰 로드 완료")
        return df

    def _extract_keywords_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """Step 2: 키워드 추출 (배치)"""
        print("\n" + "=" * 60)
        if self.use_chunking:
            print("[Step 2] 키워드 추출 (청킹 + MeCab)")
        else:
            print("[Step 2] 키워드 추출 (MeCab)")
        print("=" * 60)

        texts = df["리뷰내용"].astype(str).tolist()

        if self.use_chunking:
            if self._chunker is None:
                from ..analysis import ClauseChunker

                self._chunker = ClauseChunker()
                print("   → 절 단위 청킹 활성화")

            results = self.keyword_extractor.extract_batch_with_chunking(
                texts, chunker=self._chunker
            )
            keywords_list = [r["flat_keywords"] for r in results]

            total_chunks = sum(len(r["chunks"]) for r in results)
            print(f"   → 총 {total_chunks:,}개 청크 생성")
        else:
            if self.use_parallel:
                keywords_list = self.keyword_extractor.extract_batch_parallel(
                    texts, n_jobs=self.n_jobs, verbose=0
                )
            else:
                keywords_list = self.keyword_extractor.extract_batch(texts)

        df["keywords"] = keywords_list

        # 부정 리뷰 키워드 제거
        if self._negative_pattern_regex:
            df["is_negative"] = (
                df["리뷰내용"]
                .astype(str)
                .str.contains(self._negative_pattern_regex, na=False)
            )
            df["keywords"] = df.apply(
                lambda row: [] if row.get("is_negative", False) else row["keywords"],
                axis=1,
            )

        total_keywords = sum(len(kw) for kw in df["keywords"])
        self.stats["total_keywords"] = total_keywords
        print(f"✅ 총 {total_keywords:,}개 키워드 추출")
        return df

    def _aggregate_keywords(self, df: pd.DataFrame) -> pd.DataFrame:
        """Step 3: 지점별 키워드 집계"""
        print("\n" + "=" * 60)
        print("[Step 3] 지점별 키워드 집계 (가중치 적용)")
        print("=" * 60)

        keywords_df = self.keyword_aggregator.aggregate(df)
        print(f"✅ {len(keywords_df)}개 지점 키워드 집계 완료")
        return keywords_df

    def _generate_summaries(
        self, keywords_df: pd.DataFrame, reviews_df: pd.DataFrame, output_dir: str
    ) -> dict:
        """AI 요약 생성 + 결과 저장"""
        print("\n" + "=" * 60)
        print("[Step 3] AI 요약 생성")
        print("=" * 60)

        summary_rows = []
        total = len(keywords_df)

        branch_name_cache: dict[int, str] = {}
        if "지점명" in reviews_df.columns:
            branch_name_cache = (
                reviews_df.groupby("지점번호")["지점명"].first().to_dict()
            )

        for i, (_, row) in enumerate(keywords_df.iterrows(), 1):
            if i % 50 == 0:
                print(f"   {i}/{total} 처리 중...")

            branch_id = row["branch_id"]
            keywords = row["keywords"]
            review_count = row["review_count"]

            branch_name = branch_name_cache.get(branch_id)

            representative_reviews = self._get_representative_reviews(
                reviews_df, branch_id, keywords[:10]
            )

            top_helpful_reviews = self._extract_top_helpful_reviews(
                reviews_df, branch_id
            )

            branch_df = reviews_df[reviews_df["지점번호"] == branch_id]
            summary = self._generate_summary(
                keywords,
                review_count,
                representative_reviews,
                branch_name,
                branch_id,
                top_helpful_reviews=top_helpful_reviews,
                branch_df=branch_df,
            )

            top_tags = self._get_top_tags_for_branch(branch_id)

            summary_rows.append(
                {
                    "지점번호": branch_id,
                    "리뷰수": review_count,
                    "TOP3태그": top_tags[:3],
                    "AI요약": summary,
                }
            )

        supabase_data = []
        for row in summary_rows:
            supabase_data.append(
                {
                    "branch_id": row["지점번호"],
                    "ai_summary": row["AI요약"],
                    "keywords": row["TOP3태그"],
                    "review_count": row["리뷰수"],
                }
            )

        self._save_summaries_to_db(supabase_data)

        self.stats["summaries_generated"] = len(summary_rows)
        return {"supabase_data": supabase_data}

    def _save_summaries_to_db(self, summaries: list[dict]):
        """요약을 DB에 저장"""
        try:
            from supabase_client import upsert_branch_summary
        except ImportError:
            print("   ⚠️ DB 저장 스킵 (supabase_client 임포트 실패)")
            return

        saved = 0
        for summary in summaries:
            branch_id = summary["branch_id"]
            keywords = summary.get("keywords", [])

            try:
                upsert_branch_summary(
                    {
                        "branch_id": branch_id,
                        "review_count": summary["review_count"],
                        "keyword_1": keywords[0] if len(keywords) > 0 else None,
                        "keyword_2": keywords[1] if len(keywords) > 1 else None,
                        "keyword_3": keywords[2] if len(keywords) > 2 else None,
                        "summary_all": summary["ai_summary"],
                        "status": "draft",
                    }
                )
                saved += 1
            except Exception as e:
                print(f"   ⚠️ DB 저장 오류 (지점 {branch_id}): {e}")

        print(f"   💾 {saved}/{len(summaries)}개 저장 완료")

    def _get_representative_reviews(
        self, df: pd.DataFrame, branch_id: int, keywords: list[str]
    ) -> list[str]:
        """지점별 대표 리뷰 추출"""
        branch_df = df[df["지점번호"] == branch_id].copy()

        if branch_df.empty:
            return []

        def count_keywords(text):
            if not isinstance(text, str):
                return 0
            return sum(1 for kw in keywords if kw in text)

        branch_df["kw_count"] = branch_df["리뷰내용"].apply(count_keywords)
        top_reviews = branch_df.nlargest(5, "kw_count")["리뷰내용"].tolist()

        return [str(r)[:100] for r in top_reviews if r]

    def _extract_top_helpful_reviews(
        self, df: pd.DataFrame, branch_id: int, top_n: int = 10
    ) -> list[dict] | None:
        """도움돼요수 상위 리뷰 추출"""
        if df is None or df.empty:
            return None

        branch_df = df[df["지점번호"] == branch_id].copy()

        if branch_df.empty or "도움돼요수" not in branch_df.columns:
            return None

        top_helpful_df = branch_df.nlargest(top_n, "도움돼요수")
        result = []

        for _, row in top_helpful_df.iterrows():
            helpful_count = int(row.get("도움돼요수", 0))
            if helpful_count >= 1:
                result.append(
                    {
                        "review": str(row.get("리뷰내용", ""))[:200],
                        "helpful_count": helpful_count,
                        "tags": str(row.get("태그별감정", ""))
                        if "태그별감정" in row
                        else "",
                    }
                )

        return result if len(result) >= 3 else None

    def _generate_summary(
        self,
        keywords: list[str],
        review_count: int,
        representative_reviews: list[str],
        branch_name: str = None,
        branch_id: int = None,
        max_retries: int = 2,
        top_helpful_reviews: list[dict] | None = None,
        branch_df: pd.DataFrame = None,
    ) -> str:
        """LLM으로 요약 생성"""
        from infrastructure.llm import SummaryPromptBuilder, validate_summary

        if not keywords:
            return SummaryPromptBuilder.get_default_summary(keywords)

        if not self.llm_provider or not self.llm_provider.is_available():
            return SummaryPromptBuilder.get_default_summary(keywords)

        system_prompt, user_prompt = SummaryPromptBuilder.create_summary_prompt(
            keywords=keywords,
            review_count=review_count,
            representative_reviews=representative_reviews,
            branch_name=branch_name,
        )

        last_summary = None
        last_errors = []

        for attempt in range(max_retries + 1):
            temperature = 0.5 if attempt == 0 else 0.3

            response = self.llm_provider.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=300,
                temperature=temperature,
            )

            if not response.success:
                continue

            summary = response.content
            last_summary = summary

            is_valid, errors = validate_summary(summary)
            if is_valid:
                return summary

            last_errors = errors
            if attempt < max_retries:
                continue

        if last_summary:
            branch = branch_name or "지점"
            errors_str = "; ".join(last_errors)
            print(f"   ⚠️ [{branch}] 검증 경고 (재시도 {max_retries}회): {errors_str}")
            return last_summary

        return SummaryPromptBuilder.get_default_summary(keywords)

    # =========================================================================
    # 기간별 요약 생성
    # =========================================================================

    def _filter_by_period(self, df: pd.DataFrame, period_type: str) -> pd.DataFrame:
        """기간별 데이터 필터링"""
        if period_type == "all":
            return df

        config = PERIOD_CONFIGS.get(period_type)
        if not config or not config.get("days"):
            return df

        days = config["days"]
        cutoff_date = datetime.now() - timedelta(days=days)

        date_columns = ["등록일시", "리뷰일자", "created_at", "review_date"]
        date_col = None

        for col in date_columns:
            if col in df.columns:
                date_col = col
                break

        if not date_col:
            print("   ⚠️ 날짜 컬럼을 찾을 수 없어 전체 데이터 사용")
            return df

        df_copy = df.copy()
        df_copy[date_col] = pd.to_datetime(df_copy[date_col], errors="coerce")
        filtered = df_copy[df_copy[date_col] >= cutoff_date]

        label = config["label"]
        print(f"   {period_type} ({label}): {len(filtered):,}/{len(df):,}개 리뷰")

        return filtered

    def _generate_summaries_by_period(
        self, keywords_df: pd.DataFrame, reviews_df: pd.DataFrame, output_dir: str
    ) -> dict:
        """기간별 요약 생성"""
        print("\n" + "=" * 60)
        print("[Step 3] 기간별 AI 요약 생성")
        print("=" * 60)

        all_results = {}

        for period_type, config in PERIOD_CONFIGS.items():
            print(f"\n=== {config['label']} 요약 생성 ({period_type}) ===")

            period_df = self._filter_by_period(reviews_df, period_type)

            if period_df.empty:
                print(f"   {period_type}: 데이터 없음, 스킵")
                continue

            period_keywords_df = self.keyword_aggregator.aggregate(period_df)

            results = self._generate_summaries_for_period(
                period_keywords_df, period_df, output_dir, period_type
            )

            all_results[period_type] = results

        self.stats["period_summaries"] = {
            period: len(results.get("supabase_data", []))
            for period, results in all_results.items()
        }

        return all_results

    def _generate_summaries_for_period(
        self,
        keywords_df: pd.DataFrame,
        reviews_df: pd.DataFrame,
        output_dir: str,
        period_type: str,
    ) -> dict:
        """특정 기간의 요약 생성"""
        summary_rows = []
        total = len(keywords_df)

        branch_name_cache: dict[int, str] = {}
        if "지점명" in reviews_df.columns:
            branch_name_cache = (
                reviews_df.groupby("지점번호")["지점명"].first().to_dict()
            )

        for i, (_, row) in enumerate(keywords_df.iterrows(), 1):
            if i % 50 == 0:
                print(f"   {i}/{total} 처리 중...")

            branch_id = row["branch_id"]
            keywords = row["keywords"]
            review_count = row["review_count"]

            branch_name = branch_name_cache.get(branch_id)

            representative_reviews = self._get_representative_reviews(
                reviews_df, branch_id, keywords[:10]
            )

            top_helpful_reviews = self._extract_top_helpful_reviews(
                reviews_df, branch_id
            )

            branch_df = reviews_df[reviews_df["지점번호"] == branch_id]

            summary = self._generate_summary(
                keywords,
                review_count,
                representative_reviews,
                branch_name,
                branch_id,
                top_helpful_reviews=top_helpful_reviews,
                branch_df=branch_df,
            )

            top_tags = self._get_top_tags_for_branch(branch_id)

            summary_rows.append(
                {
                    "지점번호": branch_id,
                    "리뷰수": review_count,
                    "TOP3태그": top_tags[:3],
                    "AI요약": summary,
                }
            )

        supabase_data = []
        for row in summary_rows:
            supabase_data.append(
                {
                    "branch_id": row["지점번호"],
                    "ai_summary": row["AI요약"],
                    "keywords": row["TOP3태그"],
                    "review_count": row["리뷰수"],
                    "period_type": period_type,
                }
            )

        self._save_period_summaries_to_db(supabase_data, period_type)

        return {"supabase_data": supabase_data}

    def _save_period_summaries_to_db(self, summaries: list[dict], period_type: str):
        """기간별 요약을 DB에 저장"""
        try:
            from supabase_client import upsert_summary_with_period
        except ImportError:
            print("   ⚠️ DB 저장 스킵 (supabase_client 임포트 실패)")
            return

        saved = 0
        for summary in summaries:
            try:
                upsert_summary_with_period(
                    branch_id=summary["branch_id"],
                    period_type=period_type,
                    ai_summary=summary["ai_summary"],
                    keywords=summary["keywords"],
                    review_count=summary["review_count"],
                )
                saved += 1
            except Exception as e:
                print(f"   ⚠️ DB 저장 오류 (지점 {summary['branch_id']}): {e}")

        print(f"   💾 {period_type} 요약 {saved}/{len(summaries)}개 DB 저장")

    # =========================================================================
    # 태그 분류
    # =========================================================================

    def _classify_tags_for_summary(self, df: pd.DataFrame):
        """요약 생성을 위한 태그+감정 분류 (HybridClassifier 사용)"""
        print("\n" + "=" * 60)
        print("[Step 3] 태그+감정 분류 (HybridClassifier)")
        print("=" * 60)

        if self._hybrid_classifier is None:
            try:
                from ..analysis import HybridClassifier

                self._hybrid_classifier = HybridClassifier(lazy_load=True)
                print("   → HybridClassifier 로딩")
            except ImportError as e:
                print(f"   ⚠️ HybridClassifier 로드 실패: {e}")
                return

        branch_data: dict[int, list[dict]] = {}

        for _, row in df.iterrows():
            branch_id = row.get("지점번호")
            review = str(row.get("리뷰내용", ""))
            keywords = row.get("keywords", [])

            if not branch_id or not review:
                continue

            if branch_id not in branch_data:
                branch_data[branch_id] = []

            branch_data[branch_id].append({"review": review, "keywords": keywords})

        print(f"   → {len(branch_data)}개 지점의 리뷰 수집")

        total_reviews = sum(len(reviews) for reviews in branch_data.values())
        print(f"   → 총 {total_reviews:,}개 리뷰 분석 중...")

        processed = 0
        for branch_id, reviews in branch_data.items():
            tag_sentiment: dict[str, dict[str, list[str]]] = {}

            for item in reviews:
                result = self._hybrid_classifier.classify_review(
                    review=item["review"], keywords=item["keywords"]
                )

                for tag, sentiments in result.items():
                    if tag not in tag_sentiment:
                        tag_sentiment[tag] = {
                            "positive": [],
                            "negative": [],
                            "neutral": [],
                        }

                    for sentiment_type in ["positive", "negative", "neutral"]:
                        for kw in sentiments.get(sentiment_type, []):
                            if kw not in tag_sentiment[tag][sentiment_type]:
                                tag_sentiment[tag][sentiment_type].append(kw)

                processed += 1
                if processed % 500 == 0:
                    print(f"   {processed:,}/{total_reviews:,} 처리 중...")

            self._branch_tag_sentiment_cache[branch_id] = tag_sentiment

        total_positive = sum(
            len(ts.get("positive", []))
            for ts_data in self._branch_tag_sentiment_cache.values()
            for ts in ts_data.values()
        )
        total_negative = sum(
            len(ts.get("negative", []))
            for ts_data in self._branch_tag_sentiment_cache.values()
            for ts in ts_data.values()
        )
        total_neutral = sum(
            len(ts.get("neutral", []))
            for ts_data in self._branch_tag_sentiment_cache.values()
            for ts in ts_data.values()
        )

        print("   ✅ 태그+감정 분류 완료")
        print(f"   📊 긍정: {total_positive:,}개 / 부정: {total_negative:,}개 / 중립: {total_neutral:,}개")  # noqa: E501

    def _get_top_tags_for_branch(self, branch_id: int, top_n: int = 5) -> list[str]:
        """지점별 상위 태그 그룹 반환"""
        tag_data = self._branch_tag_sentiment_cache.get(branch_id, {})

        if not tag_data:
            return []

        tag_scores = []
        for tag_name, sentiments in tag_data.items():
            if tag_name == "기타":
                continue
            positive_count = len(sentiments.get("positive", []))
            if positive_count > 0:
                tag_scores.append((tag_name, positive_count))

        tag_scores.sort(key=lambda x: x[1], reverse=True)

        return [tag for tag, _ in tag_scores[:top_n]]

    # =========================================================================
    # 태그 매핑 및 집계
    # =========================================================================

    def _aggregate_tags(self, df: pd.DataFrame):
        """태그 매핑 및 지점별 집계 (HybridClassifier 사용)"""
        print("\n" + "=" * 60)
        print("[Step 4] 태그 매핑 및 집계 (HybridClassifier)")
        print("=" * 60)

        try:
            from supabase_client import (
                create_keyword_mapping,
                get_all_categories,
                get_or_create_tag,
                upsert_branch_tags,
            )
        except ImportError as e:
            print(f"   ⚠️ 태그 집계 스킵 (모듈 임포트 실패): {e}")
            return

        # HybridClassifier 초기화 (없으면 생성)
        if self._hybrid_classifier is None:
            try:
                from ..analysis import HybridClassifier

                self._hybrid_classifier = HybridClassifier(lazy_load=True)
            except ImportError as e:
                print(f"   ⚠️ HybridClassifier 로드 실패: {e}")
                return

        try:
            categories = get_all_categories()
            category_id_map = {c["name"]: c["id"] for c in categories}
        except Exception:
            category_id_map = {}

        branch_keywords: dict[int, dict[str, int]] = {}

        for _, row in df.iterrows():
            branch_id = row.get("지점번호")
            keywords = row.get("keywords", [])

            if not branch_id or not keywords:
                continue

            if branch_id not in branch_keywords:
                branch_keywords[branch_id] = {}

            for kw in keywords:
                branch_keywords[branch_id][kw] = (
                    branch_keywords[branch_id].get(kw, 0) + 1
                )

        print(f"   {len(branch_keywords)}개 지점의 키워드 수집 완료")

        all_unique_keywords = set()
        for kw_counts in branch_keywords.values():
            all_unique_keywords.update(kw_counts.keys())

        all_unique_keywords = list(all_unique_keywords)
        print(f"   → 고유 키워드 {len(all_unique_keywords):,}개")

        keyword_tag_map: dict[str, tuple] = {}

        # HybridClassifier로 키워드 분류
        print("   → HybridClassifier 태그 + 감정 분류 중...")
        classifications = self._hybrid_classifier.classify_keywords(all_unique_keywords)
        for kw, (tag_group, score, sentiment) in zip(
            all_unique_keywords, classifications, strict=False
        ):
            keyword_tag_map[kw] = (tag_group, score, sentiment)
        print(f"   → {len(keyword_tag_map):,}개 키워드 분류 완료")

        tag_cache: dict[str, int] = {}
        mapped_count = 0
        positive_count = 0
        negative_count = 0

        for branch_id, kw_counts in branch_keywords.items():
            branch_tags = []

            for keyword, count in kw_counts.items():
                tag_group, score, sentiment = keyword_tag_map.get(
                    keyword, ("기타", 0.0, "positive")
                )
                tag_name = tag_group

                if sentiment == "positive":
                    positive_count += count
                elif sentiment == "negative":
                    negative_count += count

                if tag_name not in tag_cache:
                    category_name = tag_group
                    category_id = category_id_map.get(category_name)

                    try:
                        tag = get_or_create_tag(tag_name, category_id, sentiment)
                        if tag and tag.get("id"):
                            tag_cache[tag_name] = tag["id"]
                            create_keyword_mapping(keyword, tag["id"], is_auto=True)
                    except Exception:
                        continue

                tag_id = tag_cache.get(tag_name)
                if tag_id:
                    weighted_score = count * score
                    branch_tags.append(
                        {
                            "tag_id": tag_id,
                            "count": count,
                            "weighted_score": weighted_score,
                        }
                    )
                    mapped_count += 1

            if branch_tags:
                with contextlib.suppress(Exception):
                    upsert_branch_tags(branch_id, "all", branch_tags)

        print(
            f"   ✅ 태그 매핑 완료: {mapped_count}개 키워드 → {len(tag_cache)}개 태그"
        )
        print(f"   📊 감정 분포: 긍정 {positive_count:,}개 / 부정 {negative_count:,}개")


# =============================================================================
# IncrementalPipeline: API 증분 처리
# =============================================================================


class IncrementalPipeline(BasePipeline):
    """
    증분 업데이트 파이프라인

    API에서 신규 리뷰를 받아 기존 키워드 점수에 증분 업데이트

    스케줄러에서 주기적으로 호출:
    1. Carmore API에서 신규 리뷰 조회
    2. 전처리 (빈 리뷰, 욕설, 광고 필터)
    3. 감정분석
    4. 키워드 추출 + 가중치 계산
    5. branch_keywords 테이블 업데이트
    6. 변화 감지 시 → AI 요약 재생성
    """

    def __init__(self):
        super().__init__()

        self.keyword_manager = KeywordScoreManager()
        self.api_client = None

        self._init_api_client()

    def _init_api_client(self):
        """Carmore API 클라이언트 초기화"""
        try:
            from clients import CarmoreAPIClient

            self.api_client = CarmoreAPIClient()
            if self.api_client.health_check():
                logger.info("Carmore API 연결 완료")
            else:
                logger.warning("Carmore API 연결 실패 - 헬스체크 실패")
        except Exception as e:
            logger.warning(f"Carmore API 초기화 실패: {e}")

    # =========================================================================
    # DB 연동
    # =========================================================================

    def get_last_sync_info(self, branch_id: int | None = None) -> dict:
        """마지막 동기화 정보 조회"""
        if not self.supabase_client:
            return {}

        try:
            query = self.supabase_client.table("sync_status").select("*")
            if branch_id:
                query = query.eq("branch_id", branch_id)
            else:
                query = query.is_("branch_id", "null")

            result = query.execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"동기화 정보 조회 실패: {e}")
            return {}

    def update_sync_status(
        self,
        branch_id: int | None,
        last_review_id: int,
        last_review_date: datetime,
        review_count: int,
        keyword_count: int,
    ):
        """동기화 상태 업데이트"""
        if not self.supabase_client:
            return

        try:
            data = {
                "branch_id": branch_id,
                "last_review_id": last_review_id,
                "last_review_date": last_review_date.isoformat()
                if last_review_date
                else None,
                "last_sync_at": datetime.now().isoformat(),
                "review_count": review_count,
                "keyword_count": keyword_count,
            }

            self.supabase_client.table("sync_status").upsert(
                data, on_conflict="branch_id"
            ).execute()
        except Exception as e:
            logger.error(f"동기화 상태 업데이트 실패: {e}")

    def load_branch_keywords(self, branch_id: int) -> list[dict]:
        """DB에서 지점 키워드 로드"""
        if not self.supabase_client:
            return []

        try:
            result = (
                self.supabase_client.table("branch_keywords")
                .select("*")
                .eq("branch_id", branch_id)
                .execute()
            )
            return result.data
        except Exception as e:
            logger.error(f"키워드 로드 실패: {e}")
            return []

    def save_branch_keywords(self, branch_id: int, keywords_data: list[dict]):
        """DB에 지점 키워드 저장"""
        if not self.supabase_client:
            return

        try:
            for kw_data in keywords_data:
                self.supabase_client.table("branch_keywords").upsert(
                    kw_data, on_conflict="branch_id,keyword"
                ).execute()
            logger.info(f"지점 {branch_id}: {len(keywords_data)}개 키워드 저장")
        except Exception as e:
            logger.error(f"키워드 저장 실패: {e}")

    def get_old_top_keywords(self, branch_id: int, limit: int = 10) -> list[str]:
        """이전 TOP 키워드 조회"""
        if not self.supabase_client:
            return []

        try:
            result = (
                self.supabase_client.table("branch_keywords")
                .select("keyword")
                .eq("branch_id", branch_id)
                .order("weighted_score", desc=True)
                .limit(limit)
                .execute()
            )
            return [r["keyword"] for r in result.data]
        except Exception as e:
            logger.error(f"TOP 키워드 조회 실패: {e}")
            return []

    # =========================================================================
    # 요약 재생성
    # =========================================================================

    def regenerate_summary_if_needed(self, branch_id: int, old_keywords: list[str]):
        """키워드 변화 시 요약 재생성"""
        if self.keyword_manager.detect_significant_change(branch_id, old_keywords):
            logger.info(f"지점 {branch_id}: 키워드 변화 감지 → 요약 재생성 예정")
            self._mark_summary_for_update(branch_id)

    def _mark_summary_for_update(self, branch_id: int):
        """요약 재생성 예정 표시"""
        if not self.supabase_client:
            return

        try:
            self.supabase_client.table("sync_status").upsert(
                {
                    "branch_id": branch_id,
                    "next_summary_update_at": datetime.now().isoformat(),
                },
                on_conflict="branch_id",
            ).execute()
        except Exception as e:
            logger.error(f"요약 업데이트 표시 실패: {e}")

    # =========================================================================
    # 메인 처리 로직
    # =========================================================================

    def process_reviews(self, reviews: list[dict]) -> dict:
        """
        리뷰 목록 처리 (메인 진입점)

        Args:
            reviews: API에서 받은 리뷰 목록

        Returns:
            처리 결과 통계
        """
        stats = {
            "total": len(reviews),
            "filtered": 0,
            "negative": 0,
            "processed": 0,
            "keywords_extracted": 0,
            "branches_updated": set(),
        }

        if not reviews:
            logger.info("처리할 리뷰 없음")
            return stats

        logger.info(f"=== 증분 파이프라인 시작: {len(reviews)}개 리뷰 ===")

        branch_reviews: dict[int, list[dict]] = {}

        for review in reviews:
            # 1. 전처리 (필터링) - BasePipeline에서 상속
            processed = self.preprocess_review(review)
            if not processed:
                stats["filtered"] += 1
                continue

            # 2. 감정분석 - BasePipeline에서 상속
            is_valid, sentiment_score, sentiment = self.is_valid_sentiment(processed)
            processed["sentiment_score"] = sentiment_score
            processed["sentiment"] = sentiment

            if sentiment == "positive":
                stats["positive"] = stats.get("positive", 0) + 1
            elif sentiment == "negative":
                stats["negative"] = stats.get("negative", 0) + 1
            else:
                stats["neutral"] = stats.get("neutral", 0) + 1

            branch_id = processed.get("지점번호") or processed.get("branch_id")
            if branch_id:
                if branch_id not in branch_reviews:
                    branch_reviews[branch_id] = []
                branch_reviews[branch_id].append(processed)

        # 3. 지점별 처리
        for branch_id, reviews_list in branch_reviews.items():
            self._process_branch_reviews(branch_id, reviews_list, stats)

        processed = stats["processed"]
        branches = len(stats["branches_updated"])
        logger.info(f"=== 처리 완료: {processed}개 리뷰, {branches}개 지점 ===")

        return stats

    def _process_branch_reviews(self, branch_id: int, reviews: list[dict], stats: dict):
        """지점별 리뷰 처리"""
        old_keywords = self.get_old_top_keywords(branch_id)
        existing_kw_data = self.load_branch_keywords(branch_id)
        self.keyword_manager.load_from_db(branch_id, existing_kw_data)

        last_review_id = 0
        last_review_date = None

        for review in reviews:
            text = review.get("리뷰내용", "") or review.get("content", "")

            # 키워드 추출 - BasePipeline에서 상속
            keywords = self.extract_keywords(text)
            if not keywords:
                continue

            review_date = review.get("등록일시") or review.get("created_at")
            if isinstance(review_date, str):
                try:
                    review_date = datetime.fromisoformat(
                        review_date.replace("Z", "+00:00")
                    )
                except Exception:
                    review_date = datetime.now()

            self.keyword_manager.update_keywords(
                branch_id=branch_id, keywords=keywords, review_date=review_date
            )

            stats["processed"] += 1
            stats["keywords_extracted"] += len(keywords)

            review_id = review.get("리뷰번호") or review.get("id", 0)
            if review_id > last_review_id:
                last_review_id = review_id
                last_review_date = review_date

        self.keyword_manager.apply_decay_to_all()

        keywords_to_save = self.keyword_manager.export_for_db(branch_id)
        self.save_branch_keywords(branch_id, keywords_to_save)

        self.update_sync_status(
            branch_id=branch_id,
            last_review_id=last_review_id,
            last_review_date=last_review_date,
            review_count=len(reviews),
            keyword_count=len(keywords_to_save),
        )

        self.regenerate_summary_if_needed(branch_id, old_keywords)

        stats["branches_updated"].add(branch_id)

    # =========================================================================
    # API 연동 (Carmore)
    # =========================================================================

    def fetch_new_reviews_from_api(
        self, since: datetime | None = None, branch_ids: list[int] | None = None
    ) -> list[dict]:
        """Carmore API에서 신규 리뷰 조회"""
        if not self.api_client:
            logger.error("API 클라이언트 미초기화")
            return []

        all_reviews = []

        if branch_ids:
            target_branches = branch_ids
        else:
            affiliates_response = self.api_client.get_affiliates(
                location_type="PARTNERS"
            )
            if not affiliates_response.success:
                logger.error(f"제휴사 목록 조회 실패: {affiliates_response.error}")
                return []

            target_branches = []
            affiliates = affiliates_response.data
            if isinstance(affiliates, list):
                for aff in affiliates:
                    branch_id = (
                        aff.get("affiliateBranchIndex")
                        or aff.get("branchIndex")
                        or aff.get("id")
                    )
                    if branch_id:
                        target_branches.append(branch_id)

            logger.info(f"총 {len(target_branches)}개 지점에서 리뷰 조회 예정")

        for branch_id in target_branches:
            try:
                response = self.api_client.get_reviews(
                    branch_id=branch_id, review_type="PARTNERS", page=1, page_size=100
                )

                if not response.success:
                    logger.warning(f"지점 {branch_id} 리뷰 조회 실패: {response.error}")
                    continue

                reviews_data = response.data
                reviews = []

                if isinstance(reviews_data, list):
                    reviews = reviews_data
                elif isinstance(reviews_data, dict):
                    reviews = reviews_data.get("reviews", [])

                for review in reviews:
                    converted = self._convert_api_review(review, branch_id)
                    if converted:
                        if since:
                            review_date = converted.get("등록일시")
                            if review_date:
                                if isinstance(review_date, str):
                                    review_date = datetime.fromisoformat(
                                        review_date.replace("Z", "+00:00")
                                    )
                                if review_date <= since:
                                    continue
                        all_reviews.append(converted)

            except Exception as e:
                logger.error(f"지점 {branch_id} 처리 중 에러: {e}")
                continue

        logger.info(f"총 {len(all_reviews)}개 리뷰 조회 완료")
        return all_reviews

    def _convert_api_review(self, api_review: dict, branch_id: int) -> dict | None:
        """API 응답 형식을 파이프라인 형식으로 변환"""
        try:
            content = api_review.get("opinion") or ""

            if not content or len(content.strip()) < 5:
                return None

            created_at = api_review.get("createdAt") or datetime.now().isoformat()
            helpful_count = api_review.get("recommend") or 0

            branch_eval = api_review.get("branchEvaluation") or 0
            car_eval = api_review.get("carEvaluation") or 0
            take_eval = api_review.get("takeEvaluation") or 0

            if branch_eval:
                rating = float(branch_eval)
            elif car_eval or take_eval:
                evals = [e for e in [branch_eval, car_eval, take_eval] if e]
                rating = sum(evals) / len(evals) if evals else 0.0
            else:
                rating = 0.0

            branch_name = api_review.get("branchName") or ""
            company_name = api_review.get("companyName") or ""

            reservation = api_review.get("reservation") or {}
            car_model = reservation.get("carModel") or ""

            return {
                "리뷰번호": None,
                "지점번호": branch_id,
                "지점명": f"{company_name} {branch_name}".strip(),
                "리뷰내용": content.strip(),
                "등록일시": created_at,
                "리뷰상태": "normal",
                "도움돼요수": helpful_count,
                "지점평점(친절/편의성)": rating,
                "차종": car_model,
                "작성자": api_review.get("writer") or "",
            }

        except Exception as e:
            logger.warning(f"리뷰 변환 실패: {e}")
            return None

    def run(self) -> dict:
        """증분 파이프라인 실행"""
        logger.info("=== 증분 파이프라인 시작 ===")

        sync_info = self.get_last_sync_info()
        since = None
        if sync_info.get("last_review_date"):
            since = datetime.fromisoformat(sync_info["last_review_date"])

        reviews = self.fetch_new_reviews_from_api(since)

        if not reviews:
            logger.info("신규 리뷰 없음")
            return {"total": 0, "processed": 0, "message": "신규 리뷰 없음"}

        stats = self.process_reviews(reviews)

        return stats


# =============================================================================
# KeywordScoreManager (증분 파이프라인용)
# =============================================================================


class KeywordScoreManager:
    """
    키워드 점수 관리자

    증분 업데이트를 위한 키워드 점수 계산 및 관리
    """

    def __init__(self):
        self.branch_keywords: dict[int, dict[str, dict]] = {}

    def load_from_db(self, branch_id: int, keywords_data: list[dict]):
        """DB 데이터로부터 키워드 로드"""
        if branch_id not in self.branch_keywords:
            self.branch_keywords[branch_id] = {}

        for kw_data in keywords_data:
            keyword = kw_data.get("keyword")
            if keyword:
                self.branch_keywords[branch_id][keyword] = {
                    "count": kw_data.get("count", 0),
                    "last_seen": kw_data.get("last_seen"),
                }

    def update_keywords(
        self, branch_id: int, keywords: list[str], review_date: datetime = None
    ):
        """키워드 점수 업데이트 (빈도 기반)"""
        if branch_id not in self.branch_keywords:
            self.branch_keywords[branch_id] = {}

        for keyword in keywords:
            if keyword not in self.branch_keywords[branch_id]:
                self.branch_keywords[branch_id][keyword] = {
                    "count": 0,
                    "last_seen": None,
                }

            kw_data = self.branch_keywords[branch_id][keyword]
            kw_data["count"] += 1
            kw_data["last_seen"] = (
                review_date.isoformat() if review_date else datetime.now().isoformat()
            )

    def apply_decay_to_all(self):
        """시간 감쇠 적용 (현재 미사용)"""
        pass

    def get_top_keywords(self, branch_id: int, limit: int = 10) -> list[dict]:
        """상위 키워드 반환 (빈도 기준)"""
        keywords = self.branch_keywords.get(branch_id, {})

        sorted_keywords = sorted(
            keywords.items(), key=lambda x: x[1]["count"], reverse=True
        )[:limit]

        return [{"keyword": kw, **data} for kw, data in sorted_keywords]

    def detect_significant_change(
        self, branch_id: int, old_keywords: list[str], threshold: float = 0.3
    ) -> bool:
        """키워드 변화 감지"""
        new_top = self.get_top_keywords(branch_id, len(old_keywords))
        new_keywords = [kw["keyword"] for kw in new_top]

        if not old_keywords:
            return bool(new_keywords)

        old_set = set(old_keywords)
        new_set = set(new_keywords)

        changed = len(old_set.symmetric_difference(new_set))
        change_ratio = changed / max(len(old_set), len(new_set), 1)

        return change_ratio >= threshold

    def export_for_db(self, branch_id: int) -> list[dict]:
        """DB 저장용 데이터 내보내기"""
        keywords = self.branch_keywords.get(branch_id, {})

        return [
            {
                "branch_id": branch_id,
                "keyword": keyword,
                "count": data["count"],
                "last_seen": data["last_seen"],
            }
            for keyword, data in keywords.items()
        ]


# =============================================================================
# 테스트
# =============================================================================

if __name__ == "__main__":
    print("=== 파이프라인 테스트 ===\n")

    # 증분 파이프라인 테스트
    pipeline = IncrementalPipeline()

    test_reviews = [
        {
            "리뷰번호": 1,
            "지점번호": 1234,
            "리뷰내용": "정말 친절하고 깨끗한 차량이었어요. 가격도 합리적이고 서비스도 최고였습니다.",  # noqa: E501
            "등록일시": datetime.now().isoformat(),
            "도움돼요수": 5,
            "지점평점(친절/편의성)": 4.8,
            "리뷰상태": "정상",
        },
        {
            "리뷰번호": 2,
            "지점번호": 1234,
            "리뷰내용": "차량 상태가 아주 좋았고 직원분들도 친절했어요. 다음에도 이용하겠습니다.",  # noqa: E501
            "등록일시": (datetime.now() - timedelta(days=10)).isoformat(),
            "도움돼요수": 3,
            "지점평점(친절/편의성)": 4.5,
            "리뷰상태": "정상",
        },
        {
            "리뷰번호": 3,
            "지점번호": 1234,
            "리뷰내용": "별로예요. 차가 더러웠어요.",
            "등록일시": datetime.now().isoformat(),
            "도움돼요수": 0,
            "지점평점(친절/편의성)": 2.0,
            "리뷰상태": "정상",
        },
        {
            "리뷰번호": 4,
            "지점번호": 5678,
            "리뷰내용": "연락주세요 010-1234-5678",
            "등록일시": datetime.now().isoformat(),
            "도움돼요수": 0,
            "지점평점(친절/편의성)": 5.0,
            "리뷰상태": "정상",
        },
    ]

    stats = pipeline.process_reviews(test_reviews)
    print(f"\n결과: {stats}")
