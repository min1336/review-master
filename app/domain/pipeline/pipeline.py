"""
통합 파이프라인 모듈 (비동기 + DTO 기반)

BasePipeline: 공통 기능 (키워드 추출, 전처리, 감정 분석) - 비동기
BatchPipeline: DB 배치 처리 - 비동기
IncrementalPipeline: API 증분 처리 - 비동기

Usage:
    # DB에서 데이터 로드하여 처리
    pipeline = BatchPipeline()
    result = await pipeline.run(branch_ids=[1234, 5678])

    # 증분 파이프라인
    incremental = IncrementalPipeline()
    stats = await incremental.run()
"""

from __future__ import annotations

import contextlib
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

# .env 로드
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except ImportError:
    pass

from core.config import get_settings
from core.stopwords import LexiconConfig
from infrastructure.llm import OpenAIProvider
from schemas.dto import (
    BranchKeywordsDTO,
    IncrementalStatsDTO,
    PipelineResultDTO,
    ProcessedReviewDTO,
    ReviewDTO,
)

from ..analysis import KeywordAggregator, KeywordExtractor

# 순환 참조 방지
if TYPE_CHECKING:
    from supabase import AsyncClient

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
# BasePipeline: 공통 기능 (비동기)
# =============================================================================


class BasePipeline(ABC):
    """
    파이프라인 공통 기능 베이스 클래스 (비동기)

    공통 기능:
    - MeCab 키워드 추출
    - 전처리/필터링 (욕설, 광고, 빈 리뷰)
    - 감정 분석 (Lexicon 기반)
    - Supabase 연동 (비동기)
    """

    def __init__(self) -> None:
        self.mecab = None
        self._supabase_client: AsyncClient | None = None
        self._hybrid_classifier = None

        self._init_mecab()

    def _init_mecab(self) -> None:
        """MeCab 초기화"""
        try:
            import mecab

            self.mecab = mecab.MeCab()
            logger.info("MeCab 초기화 완료")
        except ImportError:
            logger.warning("MeCab 미설치 - 정규식 폴백 사용")

    async def _get_supabase(self) -> AsyncClient:
        """Supabase 비동기 클라이언트 획득 (lazy loading)"""
        if self._supabase_client is None:
            try:
                from repository.session import get_client

                self._supabase_client = await get_client()
                logger.info("Supabase 비동기 연결 완료")
            except Exception as e:
                logger.warning(f"Supabase 연결 실패: {e}")
                raise
        return self._supabase_client

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

    def preprocess_review(self, review: ReviewDTO) -> ReviewDTO | None:
        """
        리뷰 전처리 (필터링)

        Args:
            review: ReviewDTO 객체

        Returns:
            통과한 ReviewDTO 또는 None (필터됨)
        """
        # 1. 기본 유효성 검사
        if not review.is_valid():
            return None

        text = review.content

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

        return review

    # =========================================================================
    # 감정 분석
    # =========================================================================

    def analyze_sentiment(
        self, text: str, keywords: list[str] | None = None
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
        if self._hybrid_classifier is None:
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

    def process_review(self, review: ReviewDTO) -> ProcessedReviewDTO | None:
        """
        리뷰 처리 (전처리 + 키워드 추출 + 감정 분석)

        Args:
            review: ReviewDTO 객체

        Returns:
            ProcessedReviewDTO 또는 None (필터됨)
        """
        # 전처리
        preprocessed = self.preprocess_review(review)
        if preprocessed is None:
            return None

        # 키워드 추출
        keywords = self.extract_keywords(preprocessed.content)

        # 감정 분석
        sentiment, score = self.analyze_sentiment(preprocessed.content, keywords)

        return ProcessedReviewDTO(
            review=preprocessed,
            keywords=keywords,
            sentiment=sentiment,
            sentiment_score=score,
        )

    # =========================================================================
    # 추상 메서드
    # =========================================================================

    @abstractmethod
    async def run(self, *args, **kwargs) -> PipelineResultDTO:
        """파이프라인 실행 (비동기)"""
        pass


# =============================================================================
# BatchPipeline: DB 배치 처리 (비동기)
# =============================================================================


class BatchPipeline(BasePipeline):
    """
    배치 리뷰 분석 파이프라인 (DB 전용, 비동기)

    DB에서 리뷰를 로드하여 전체 지점의 리뷰를 분석하고 AI 요약을 생성합니다.

    사용법:
        pipeline = BatchPipeline(min_reviews=30)
        result = await pipeline.run(branch_ids=[1234, 5678])
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

        # 통계
        self._stats: dict = {}

    async def run(
        self,
        branch_ids: list[int] | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int | None = None,
        generate_period_summaries: bool = True,
    ) -> PipelineResultDTO:
        """
        파이프라인 실행 (DB 로드)

        Args:
            branch_ids: 특정 지점만 처리 (None이면 전체)
            date_from: 시작일 필터
            date_to: 종료일 필터
            limit: 최대 리뷰 수
            generate_period_summaries: 기간별 요약 생성 여부

        Returns:
            PipelineResultDTO
        """
        started_at = datetime.now()

        print("\n" + "=" * 60)
        print("🚀 리뷰 요약 파이프라인 v7.0 시작 (비동기 + DTO 기반)")
        print("=" * 60)

        try:
            # Step 1: DB에서 데이터 로드
            reviews = await self._load_from_database(
                branch_ids=branch_ids,
                date_from=date_from,
                date_to=date_to,
                limit=limit,
            )

            if not reviews:
                return PipelineResultDTO(
                    success=False,
                    total_reviews=0,
                    processed_reviews=0,
                    total_branches=0,
                    summaries_generated=0,
                    error_message="조회된 리뷰가 없습니다",
                    started_at=started_at,
                    finished_at=datetime.now(),
                )

            self._stats["total_reviews"] = len(reviews)

            # Step 2: 리뷰 처리 (전처리 + 키워드 추출 + 감정 분석)
            processed_reviews = await self._process_reviews_batch(reviews)
            self._stats["processed_reviews"] = len(processed_reviews)

            # Step 3: 지점별 키워드 집계
            branch_keywords = self._aggregate_keywords_by_branch(processed_reviews)
            self._stats["branch_count"] = len(branch_keywords)

            # Step 4: 태그+감정 분류
            await self._classify_tags_for_summary(processed_reviews)

            # Step 5: AI 요약 생성
            if generate_period_summaries:
                await self._generate_summaries_by_period(
                    branch_keywords, processed_reviews
                )
            else:
                await self._generate_summaries(branch_keywords, processed_reviews)

            # Step 6: 태그 매핑 및 집계 (DB 저장)
            await self._aggregate_tags(processed_reviews)

            # 완료
            elapsed = (datetime.now() - started_at).total_seconds()
            self._stats["elapsed_seconds"] = elapsed

            print("\n" + "=" * 60)
            print(f"✅ 파이프라인 완료! (소요 시간: {elapsed:.1f}초)")
            print("=" * 60)

            return PipelineResultDTO(
                success=True,
                total_reviews=self._stats.get("total_reviews", 0),
                processed_reviews=self._stats.get("processed_reviews", 0),
                total_branches=self._stats.get("branch_count", 0),
                summaries_generated=self._stats.get("summaries_generated", 0),
                total_duration_seconds=elapsed,
                started_at=started_at,
                finished_at=datetime.now(),
            )

        except Exception as e:
            logger.error(f"파이프라인 오류: {e}")
            return PipelineResultDTO(
                success=False,
                total_reviews=self._stats.get("total_reviews", 0),
                processed_reviews=self._stats.get("processed_reviews", 0),
                total_branches=self._stats.get("branch_count", 0),
                summaries_generated=0,
                error_message=str(e),
                started_at=started_at,
                finished_at=datetime.now(),
            )

    async def _load_from_database(
        self,
        branch_ids: list[int] | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int | None = None,
    ) -> list[ReviewDTO]:
        """
        Step 1: DB에서 리뷰 로드

        Args:
            branch_ids: 특정 지점만 조회 (None이면 전체)
            date_from: 시작일 (이 날짜 이후 리뷰만)
            date_to: 종료일 (이 날짜 이전 리뷰만)
            limit: 최대 조회 개수 (None이면 전체)

        Returns:
            ReviewDTO 리스트
        """
        print("\n" + "=" * 60)
        print("[Step 1] 데이터 로드 (Database)")
        print("=" * 60)

        client = await self._get_supabase()

        # 기본 쿼리
        query = client.table("branch_reviews").select("*")

        # 필터 적용
        if branch_ids:
            query = query.in_("branch_id", branch_ids)
            print(f"   → 지점 필터: {len(branch_ids)}개 지점")

        if date_from:
            query = query.gte("review_date", date_from.isoformat())
            print(f"   → 시작일: {date_from.strftime('%Y-%m-%d')}")

        if date_to:
            query = query.lte("review_date", date_to.isoformat())
            print(f"   → 종료일: {date_to.strftime('%Y-%m-%d')}")

        # 정렬
        query = query.order("review_date", desc=True)

        # 제한
        if limit:
            query = query.limit(limit)
            print(f"   → 최대 조회: {limit:,}개")

        # 실행
        result = await query.execute()

        if not result.data:
            print("   ⚠️ 조회된 리뷰가 없습니다")
            return []

        # ReviewDTO 변환
        reviews = [ReviewDTO.from_db_row(row) for row in result.data]

        print(f"✅ {len(reviews):,}개 리뷰 로드 완료 (DB)")
        return reviews

    async def _process_reviews_batch(
        self, reviews: list[ReviewDTO]
    ) -> list[ProcessedReviewDTO]:
        """Step 2: 리뷰 배치 처리 (전처리 + 키워드 추출 + 감정 분석)"""
        print("\n" + "=" * 60)
        print("[Step 2] 리뷰 처리 (전처리 + 키워드 + 감정)")
        print("=" * 60)

        processed_reviews: list[ProcessedReviewDTO] = []

        for review in reviews:
            processed = self.process_review(review)
            if processed:
                # 부정 리뷰 키워드 필터링
                if self._negative_pattern_regex:
                    if self._negative_pattern_regex.search(review.content):
                        processed.keywords = []
                        processed.is_negative_filtered = True

                processed_reviews.append(processed)

        total_keywords = sum(len(pr.keywords) for pr in processed_reviews)
        self._stats["total_keywords"] = total_keywords

        print(f"✅ {len(processed_reviews):,}개 리뷰 처리 완료")
        print(f"   → 총 {total_keywords:,}개 키워드 추출")

        return processed_reviews

    def _aggregate_keywords_by_branch(
        self, processed_reviews: list[ProcessedReviewDTO]
    ) -> list[BranchKeywordsDTO]:
        """Step 3: 지점별 키워드 집계"""
        print("\n" + "=" * 60)
        print("[Step 3] 지점별 키워드 집계")
        print("=" * 60)

        # 지점별 그룹화
        branch_data: dict[int, dict] = {}

        for pr in processed_reviews:
            branch_id = pr.branch_id
            if branch_id not in branch_data:
                branch_data[branch_id] = {
                    "branch_name": pr.review.branch_name,
                    "keywords": [],
                    "keyword_counts": {},
                    "review_count": 0,
                }

            branch_data[branch_id]["review_count"] += 1

            for kw in pr.keywords:
                branch_data[branch_id]["keywords"].append(kw)
                branch_data[branch_id]["keyword_counts"][kw] = (
                    branch_data[branch_id]["keyword_counts"].get(kw, 0) + 1
                )

        # BranchKeywordsDTO 생성
        result: list[BranchKeywordsDTO] = []

        for branch_id, data in branch_data.items():
            # 상위 키워드 추출 (빈도 기준)
            sorted_keywords = sorted(
                data["keyword_counts"].items(), key=lambda x: x[1], reverse=True
            )
            top_keywords = [kw for kw, _ in sorted_keywords[:20]]

            result.append(
                BranchKeywordsDTO(
                    branch_id=branch_id,
                    branch_name=data["branch_name"],
                    keywords=top_keywords,
                    review_count=data["review_count"],
                    keyword_counts=data["keyword_counts"],
                )
            )

        print(f"✅ {len(result)}개 지점 키워드 집계 완료")
        return result

    async def _classify_tags_for_summary(
        self, processed_reviews: list[ProcessedReviewDTO]
    ) -> None:
        """요약 생성을 위한 태그+감정 분류"""
        print("\n" + "=" * 60)
        print("[Step 4] 태그+감정 분류 (HybridClassifier)")
        print("=" * 60)

        if self._hybrid_classifier is None:
            try:
                from ..analysis import HybridClassifier

                self._hybrid_classifier = HybridClassifier(lazy_load=True)
                print("   → HybridClassifier 로딩")
            except ImportError as e:
                print(f"   ⚠️ HybridClassifier 로드 실패: {e}")
                return

        # 지점별 데이터 수집
        branch_data: dict[int, list[ProcessedReviewDTO]] = {}

        for pr in processed_reviews:
            branch_id = pr.branch_id
            if branch_id not in branch_data:
                branch_data[branch_id] = []
            branch_data[branch_id].append(pr)

        print(f"   → {len(branch_data)}개 지점의 리뷰 수집")

        total_reviews = sum(len(reviews) for reviews in branch_data.values())
        print(f"   → 총 {total_reviews:,}개 리뷰 분석 중...")

        processed = 0
        for branch_id, reviews in branch_data.items():
            tag_sentiment: dict[str, dict[str, list[str]]] = {}

            for pr in reviews:
                result = self._hybrid_classifier.classify_review(
                    review=pr.content, keywords=pr.keywords
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

        print("   ✅ 태그+감정 분류 완료")
        print(f"   📊 긍정: {total_positive:,}개 / 부정: {total_negative:,}개")

    async def _generate_summaries(
        self,
        branch_keywords: list[BranchKeywordsDTO],
        processed_reviews: list[ProcessedReviewDTO],
    ) -> dict:
        """AI 요약 생성 + 결과 저장 (비동기)"""
        print("\n" + "=" * 60)
        print("[Step 5] AI 요약 생성")
        print("=" * 60)

        # 지점별 리뷰 그룹화
        branch_reviews: dict[int, list[ProcessedReviewDTO]] = {}
        for pr in processed_reviews:
            if pr.branch_id not in branch_reviews:
                branch_reviews[pr.branch_id] = []
            branch_reviews[pr.branch_id].append(pr)

        summary_rows = []
        total = len(branch_keywords)

        for i, bk in enumerate(branch_keywords, 1):
            if i % 50 == 0:
                print(f"   {i}/{total} 처리 중...")

            reviews = branch_reviews.get(bk.branch_id, [])

            representative_reviews = self._get_representative_reviews(
                reviews, bk.keywords[:10]
            )

            top_helpful_reviews = self._extract_top_helpful_reviews(reviews)

            summary = self._generate_summary(
                keywords=bk.keywords,
                review_count=bk.review_count,
                representative_reviews=representative_reviews,
                branch_name=bk.branch_name,
                branch_id=bk.branch_id,
                top_helpful_reviews=top_helpful_reviews,
            )

            top_tags = self._get_top_tags_for_branch(bk.branch_id)

            summary_rows.append(
                {
                    "branch_id": bk.branch_id,
                    "review_count": bk.review_count,
                    "top_tags": top_tags[:3],
                    "ai_summary": summary,
                }
            )

        await self._save_summaries_to_db(summary_rows)

        self._stats["summaries_generated"] = len(summary_rows)
        return {"summaries": summary_rows}

    async def _generate_summaries_by_period(
        self,
        branch_keywords: list[BranchKeywordsDTO],
        processed_reviews: list[ProcessedReviewDTO],
    ) -> dict:
        """기간별 요약 생성 (비동기)"""
        print("\n" + "=" * 60)
        print("[Step 5] 기간별 AI 요약 생성")
        print("=" * 60)

        all_results = {}

        for period_type, config in PERIOD_CONFIGS.items():
            print(f"\n=== {config['label']} 요약 생성 ({period_type}) ===")

            # 기간별 필터링
            filtered_reviews = self._filter_reviews_by_period(
                processed_reviews, period_type
            )

            if not filtered_reviews:
                print(f"   {period_type}: 데이터 없음, 스킵")
                continue

            # 지점별 키워드 재집계
            period_keywords = self._aggregate_keywords_by_branch(filtered_reviews)

            results = await self._generate_summaries_for_period(
                period_keywords, filtered_reviews, period_type
            )

            all_results[period_type] = results

        self._stats["period_summaries"] = {
            period: len(results.get("summaries", []))
            for period, results in all_results.items()
        }

        return all_results

    def _filter_reviews_by_period(
        self, reviews: list[ProcessedReviewDTO], period_type: str
    ) -> list[ProcessedReviewDTO]:
        """기간별 리뷰 필터링"""
        if period_type == "all":
            return reviews

        config = PERIOD_CONFIGS.get(period_type)
        if not config or not config.get("days"):
            return reviews

        days = config["days"]
        cutoff_date = datetime.now() - timedelta(days=days)

        filtered = []
        for pr in reviews:
            if pr.review.created_at and pr.review.created_at >= cutoff_date:
                filtered.append(pr)

        label = config["label"]
        print(f"   {period_type} ({label}): {len(filtered):,}/{len(reviews):,}개 리뷰")

        return filtered

    async def _generate_summaries_for_period(
        self,
        branch_keywords: list[BranchKeywordsDTO],
        processed_reviews: list[ProcessedReviewDTO],
        period_type: str,
    ) -> dict:
        """특정 기간의 요약 생성 (비동기)"""
        # 지점별 리뷰 그룹화
        branch_reviews: dict[int, list[ProcessedReviewDTO]] = {}
        for pr in processed_reviews:
            if pr.branch_id not in branch_reviews:
                branch_reviews[pr.branch_id] = []
            branch_reviews[pr.branch_id].append(pr)

        summary_rows = []
        total = len(branch_keywords)

        for i, bk in enumerate(branch_keywords, 1):
            if i % 50 == 0:
                print(f"   {i}/{total} 처리 중...")

            reviews = branch_reviews.get(bk.branch_id, [])

            representative_reviews = self._get_representative_reviews(
                reviews, bk.keywords[:10]
            )

            top_helpful_reviews = self._extract_top_helpful_reviews(reviews)

            summary = self._generate_summary(
                keywords=bk.keywords,
                review_count=bk.review_count,
                representative_reviews=representative_reviews,
                branch_name=bk.branch_name,
                branch_id=bk.branch_id,
                top_helpful_reviews=top_helpful_reviews,
            )

            top_tags = self._get_top_tags_for_branch(bk.branch_id)

            summary_rows.append(
                {
                    "branch_id": bk.branch_id,
                    "review_count": bk.review_count,
                    "top_tags": top_tags[:3],
                    "ai_summary": summary,
                    "period_type": period_type,
                }
            )

        await self._save_period_summaries_to_db(summary_rows, period_type)

        return {"summaries": summary_rows}

    async def _save_summaries_to_db(self, summaries: list[dict]) -> None:
        """요약을 DB에 저장 (비동기)"""
        client = await self._get_supabase()

        saved = 0
        for summary in summaries:
            branch_id = summary["branch_id"]
            keywords = summary.get("top_tags", [])

            try:
                await client.table("branch_summaries").upsert(
                    {
                        "branch_id": branch_id,
                        "review_count": summary["review_count"],
                        "keyword_1": keywords[0] if len(keywords) > 0 else None,
                        "keyword_2": keywords[1] if len(keywords) > 1 else None,
                        "keyword_3": keywords[2] if len(keywords) > 2 else None,
                        "summary_all": summary["ai_summary"],
                        "status": "draft",
                    },
                    on_conflict="branch_id",
                ).execute()
                saved += 1
            except Exception as e:
                print(f"   ⚠️ DB 저장 오류 (지점 {branch_id}): {e}")

        print(f"   💾 {saved}/{len(summaries)}개 저장 완료")

    async def _save_period_summaries_to_db(
        self, summaries: list[dict], period_type: str
    ) -> None:
        """기간별 요약을 DB에 저장 (비동기)"""
        client = await self._get_supabase()

        summary_column = f"summary_{period_type}"

        saved = 0
        for summary in summaries:
            branch_id = summary["branch_id"]
            keywords = summary.get("top_tags", [])

            try:
                await client.table("branch_summaries").upsert(
                    {
                        "branch_id": branch_id,
                        "review_count": summary["review_count"],
                        "keyword_1": keywords[0] if len(keywords) > 0 else None,
                        "keyword_2": keywords[1] if len(keywords) > 1 else None,
                        "keyword_3": keywords[2] if len(keywords) > 2 else None,
                        summary_column: summary["ai_summary"],
                        "status": "draft",
                    },
                    on_conflict="branch_id",
                ).execute()
                saved += 1
            except Exception as e:
                print(f"   ⚠️ DB 저장 오류 (지점 {branch_id}): {e}")

        print(f"   💾 {period_type} 요약 {saved}/{len(summaries)}개 DB 저장")

    def _get_representative_reviews(
        self, reviews: list[ProcessedReviewDTO], keywords: list[str]
    ) -> list[str]:
        """지점별 대표 리뷰 추출"""
        if not reviews:
            return []

        # 키워드 포함 개수로 정렬
        def count_keywords(pr: ProcessedReviewDTO) -> int:
            return sum(1 for kw in keywords if kw in pr.content)

        sorted_reviews = sorted(reviews, key=count_keywords, reverse=True)
        top_reviews = sorted_reviews[:5]

        return [pr.content[:100] for pr in top_reviews if pr.content]

    def _extract_top_helpful_reviews(
        self, reviews: list[ProcessedReviewDTO], top_n: int = 10
    ) -> list[dict] | None:
        """도움돼요수 상위 리뷰 추출"""
        if not reviews:
            return None

        # like_count로 정렬
        sorted_reviews = sorted(
            reviews, key=lambda pr: pr.review.like_count, reverse=True
        )[:top_n]

        result = []
        for pr in sorted_reviews:
            helpful_count = pr.review.like_count
            if helpful_count >= 1:
                result.append(
                    {
                        "review": pr.content[:200],
                        "helpful_count": helpful_count,
                        "sentiment": pr.sentiment,
                    }
                )

        return result if len(result) >= 3 else None

    def _generate_summary(
        self,
        keywords: list[str],
        review_count: int,
        representative_reviews: list[str],
        branch_name: str | None = None,
        branch_id: int | None = None,
        max_retries: int = 2,
        top_helpful_reviews: list[dict] | None = None,
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

    async def _aggregate_tags(
        self, processed_reviews: list[ProcessedReviewDTO]
    ) -> None:
        """태그 매핑 및 지점별 집계 (비동기)"""
        print("\n" + "=" * 60)
        print("[Step 6] 태그 매핑 및 집계")
        print("=" * 60)

        client = await self._get_supabase()

        if self._hybrid_classifier is None:
            try:
                from ..analysis import HybridClassifier

                self._hybrid_classifier = HybridClassifier(lazy_load=True)
            except ImportError as e:
                print(f"   ⚠️ HybridClassifier 로드 실패: {e}")
                return

        # 카테고리 조회
        try:
            result = await client.table("tag_categories").select("*").execute()
            categories = result.data or []
            category_id_map = {c["name"]: c["id"] for c in categories}
        except Exception:
            category_id_map = {}

        # 지점별 키워드 수집
        branch_keywords: dict[int, dict[str, int]] = {}

        for pr in processed_reviews:
            branch_id = pr.branch_id
            if branch_id not in branch_keywords:
                branch_keywords[branch_id] = {}

            for kw in pr.keywords:
                branch_keywords[branch_id][kw] = (
                    branch_keywords[branch_id].get(kw, 0) + 1
                )

        print(f"   {len(branch_keywords)}개 지점의 키워드 수집 완료")

        # 고유 키워드 추출
        all_unique_keywords = set()
        for kw_counts in branch_keywords.values():
            all_unique_keywords.update(kw_counts.keys())

        all_unique_keywords_list = list(all_unique_keywords)
        print(f"   → 고유 키워드 {len(all_unique_keywords_list):,}개")

        # HybridClassifier로 키워드 분류
        keyword_tag_map: dict[str, tuple] = {}
        print("   → HybridClassifier 태그 + 감정 분류 중...")
        classifications = self._hybrid_classifier.classify_keywords(
            all_unique_keywords_list
        )
        for kw, (tag_group, score, sentiment) in zip(
            all_unique_keywords_list, classifications, strict=False
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
                        result = await client.table("tags").upsert(
                            {
                                "name": tag_name,
                                "category_id": category_id,
                                "sentiment_type": sentiment,
                            },
                            on_conflict="name",
                        ).execute()

                        if result.data and len(result.data) > 0:
                            tag = result.data[0]
                            tag_cache[tag_name] = tag["id"]

                            await client.table("keyword_mappings").upsert(
                                {
                                    "keyword": keyword,
                                    "tag_id": tag["id"],
                                    "is_auto": True,
                                },
                                on_conflict="keyword",
                            ).execute()
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
                    for tag_data in branch_tags:
                        await client.table("branch_tags").upsert(
                            {
                                "branch_id": branch_id,
                                "tag_id": tag_data["tag_id"],
                                "period_type": "all",
                                "count": tag_data["count"],
                                "weighted_score": tag_data["weighted_score"],
                            },
                            on_conflict="branch_id,tag_id,period_type",
                        ).execute()

        print(
            f"   ✅ 태그 매핑 완료: {mapped_count}개 키워드 → {len(tag_cache)}개 태그"
        )
        print(f"   📊 감정 분포: 긍정 {positive_count:,}개 / 부정 {negative_count:,}개")


# =============================================================================
# IncrementalPipeline: API 증분 처리 (비동기)
# =============================================================================


class IncrementalPipeline(BasePipeline):
    """
    증분 업데이트 파이프라인 (비동기)

    API에서 신규 리뷰를 받아 기존 키워드 점수에 증분 업데이트

    스케줄러에서 주기적으로 호출:
    1. Carmore API에서 신규 리뷰 조회
    2. 전처리 (빈 리뷰, 욕설, 광고 필터)
    3. 감정분석
    4. 키워드 추출 + 가중치 계산
    5. branch_keywords 테이블 업데이트
    6. 변화 감지 시 → AI 요약 재생성
    """

    def __init__(self) -> None:
        super().__init__()

        self.keyword_manager = KeywordScoreManager()
        self.api_client = None

        self._init_api_client()

    def _init_api_client(self) -> None:
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
    # DB 연동 (비동기)
    # =========================================================================

    async def get_last_sync_info(self, branch_id: int | None = None) -> dict:
        """마지막 동기화 정보 조회 (비동기)"""
        client = await self._get_supabase()

        try:
            query = client.table("sync_status").select("*")
            if branch_id:
                query = query.eq("branch_id", branch_id)
            else:
                query = query.is_("branch_id", "null")

            result = await query.execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"동기화 정보 조회 실패: {e}")
            return {}

    async def update_sync_status(
        self,
        branch_id: int | None,
        last_review_id: int,
        last_review_date: datetime | None,
        review_count: int,
        keyword_count: int,
    ) -> None:
        """동기화 상태 업데이트 (비동기)"""
        client = await self._get_supabase()

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

            await client.table("sync_status").upsert(
                data, on_conflict="branch_id"
            ).execute()
        except Exception as e:
            logger.error(f"동기화 상태 업데이트 실패: {e}")

    async def load_branch_keywords(self, branch_id: int) -> list[dict]:
        """DB에서 지점 키워드 로드 (비동기)"""
        client = await self._get_supabase()

        try:
            result = (
                await client.table("branch_keywords")
                .select("*")
                .eq("branch_id", branch_id)
                .execute()
            )
            return result.data
        except Exception as e:
            logger.error(f"키워드 로드 실패: {e}")
            return []

    async def save_branch_keywords(
        self, branch_id: int, keywords_data: list[dict]
    ) -> None:
        """DB에 지점 키워드 저장 (비동기)"""
        client = await self._get_supabase()

        try:
            for kw_data in keywords_data:
                await client.table("branch_keywords").upsert(
                    kw_data, on_conflict="branch_id,keyword"
                ).execute()
            logger.info(f"지점 {branch_id}: {len(keywords_data)}개 키워드 저장")
        except Exception as e:
            logger.error(f"키워드 저장 실패: {e}")

    async def get_old_top_keywords(
        self, branch_id: int, limit: int = 10
    ) -> list[str]:
        """이전 TOP 키워드 조회 (비동기)"""
        client = await self._get_supabase()

        try:
            result = (
                await client.table("branch_keywords")
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

    async def regenerate_summary_if_needed(
        self, branch_id: int, old_keywords: list[str]
    ) -> None:
        """키워드 변화 시 요약 재생성 표시 (비동기)"""
        if self.keyword_manager.detect_significant_change(branch_id, old_keywords):
            logger.info(f"지점 {branch_id}: 키워드 변화 감지 → 요약 재생성 예정")
            await self._mark_summary_for_update(branch_id)

    async def _mark_summary_for_update(self, branch_id: int) -> None:
        """요약 재생성 예정 표시 (비동기)"""
        client = await self._get_supabase()

        try:
            await client.table("sync_status").upsert(
                {
                    "branch_id": branch_id,
                    "next_summary_update_at": datetime.now().isoformat(),
                },
                on_conflict="branch_id",
            ).execute()
        except Exception as e:
            logger.error(f"요약 업데이트 표시 실패: {e}")

    # =========================================================================
    # 메인 처리 로직 (비동기)
    # =========================================================================

    async def process_reviews(
        self, reviews: list[ReviewDTO]
    ) -> IncrementalStatsDTO:
        """
        리뷰 목록 처리 (메인 진입점, 비동기)

        Args:
            reviews: ReviewDTO 목록

        Returns:
            IncrementalStatsDTO
        """
        stats = IncrementalStatsDTO(total=len(reviews))

        if not reviews:
            logger.info("처리할 리뷰 없음")
            return stats

        logger.info(f"=== 증분 파이프라인 시작: {len(reviews)}개 리뷰 ===")

        branch_reviews: dict[int, list[ProcessedReviewDTO]] = {}

        for review in reviews:
            # 리뷰 처리 (전처리 + 키워드 추출 + 감정 분석)
            processed = self.process_review(review)
            if not processed:
                stats.filtered += 1
                continue

            # 감정 통계
            if processed.sentiment == "positive":
                stats.positive += 1
            elif processed.sentiment == "negative":
                stats.negative += 1
            else:
                stats.neutral += 1

            branch_id = processed.branch_id
            if branch_id:
                if branch_id not in branch_reviews:
                    branch_reviews[branch_id] = []
                branch_reviews[branch_id].append(processed)

        # 지점별 처리
        for branch_id, reviews_list in branch_reviews.items():
            await self._process_branch_reviews(branch_id, reviews_list, stats)

        logger.info(
            f"=== 처리 완료: {stats.processed}개 리뷰, "
            f"{len(stats.branches_updated)}개 지점 ==="
        )

        return stats

    async def _process_branch_reviews(
        self,
        branch_id: int,
        reviews: list[ProcessedReviewDTO],
        stats: IncrementalStatsDTO,
    ) -> None:
        """지점별 리뷰 처리 (비동기)"""
        old_keywords = await self.get_old_top_keywords(branch_id)
        existing_kw_data = await self.load_branch_keywords(branch_id)
        self.keyword_manager.load_from_db(branch_id, existing_kw_data)

        last_review_id = 0
        last_review_date: datetime | None = None

        for processed in reviews:
            if not processed.keywords:
                continue

            review_date = processed.review.created_at or datetime.now()

            self.keyword_manager.update_keywords(
                branch_id=branch_id,
                keywords=processed.keywords,
                review_date=review_date,
            )

            stats.processed += 1
            stats.keywords_extracted += len(processed.keywords)

            review_id = processed.review.id
            if review_id > last_review_id:
                last_review_id = review_id
                last_review_date = review_date

        self.keyword_manager.apply_decay_to_all()

        keywords_to_save = self.keyword_manager.export_for_db(branch_id)
        await self.save_branch_keywords(branch_id, keywords_to_save)

        await self.update_sync_status(
            branch_id=branch_id,
            last_review_id=last_review_id,
            last_review_date=last_review_date,
            review_count=len(reviews),
            keyword_count=len(keywords_to_save),
        )

        await self.regenerate_summary_if_needed(branch_id, old_keywords)

        stats.branches_updated.add(branch_id)

    # =========================================================================
    # API 연동 (Carmore)
    # =========================================================================

    async def fetch_new_reviews_from_api(
        self, since: datetime | None = None, branch_ids: list[int] | None = None
    ) -> list[ReviewDTO]:
        """Carmore API에서 신규 리뷰 조회 (비동기)"""
        if not self.api_client:
            logger.error("API 클라이언트 미초기화")
            return []

        all_reviews: list[ReviewDTO] = []

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
                            review_date = converted.created_at
                            if review_date and review_date <= since:
                                continue
                        all_reviews.append(converted)

            except Exception as e:
                logger.error(f"지점 {branch_id} 처리 중 에러: {e}")
                continue

        logger.info(f"총 {len(all_reviews)}개 리뷰 조회 완료")
        return all_reviews

    def _convert_api_review(
        self, api_review: dict, branch_id: int
    ) -> ReviewDTO | None:
        """API 응답 형식을 ReviewDTO로 변환"""
        try:
            content = api_review.get("opinion") or ""

            if not content or len(content.strip()) < 5:
                return None

            created_at_str = api_review.get("createdAt")
            created_at = None
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(
                        created_at_str.replace("Z", "+00:00")
                    )
                except ValueError:
                    created_at = datetime.now()
            else:
                created_at = datetime.now()

            helpful_count = api_review.get("recommend") or 0

            branch_eval = api_review.get("branchEvaluation") or 0
            car_eval = api_review.get("carEvaluation") or 0
            take_eval = api_review.get("takeEvaluation") or 0

            if branch_eval:
                rating = float(branch_eval)
            elif car_eval or take_eval:
                evals = [e for e in [branch_eval, car_eval, take_eval] if e]
                rating = sum(evals) / len(evals) if evals else None
            else:
                rating = None

            branch_name = api_review.get("branchName") or ""
            company_name = api_review.get("companyName") or ""

            reservation = api_review.get("reservation") or {}
            car_model = reservation.get("carModel") or ""

            return ReviewDTO(
                id=0,
                branch_id=branch_id,
                content=content.strip(),
                branch_name=f"{company_name} {branch_name}".strip(),
                rating=rating,
                created_at=created_at,
                like_count=helpful_count,
                is_blind=False,
                car_model=car_model,
                company_name=company_name,
                status="normal",
            )

        except Exception as e:
            logger.warning(f"리뷰 변환 실패: {e}")
            return None

    async def run(
        self,
        branch_ids: list[int] | None = None,
        since: datetime | None = None,
    ) -> PipelineResultDTO:
        """
        증분 파이프라인 실행 (비동기)

        Args:
            branch_ids: 특정 지점만 처리 (None이면 전체)
            since: 이 날짜 이후 리뷰만 처리

        Returns:
            PipelineResultDTO
        """
        started_at = datetime.now()
        logger.info("=== 증분 파이프라인 시작 ===")

        try:
            # since가 없으면 마지막 동기화 시점 조회
            if since is None:
                sync_info = await self.get_last_sync_info()
                if sync_info.get("last_review_date"):
                    since = datetime.fromisoformat(sync_info["last_review_date"])

            # API에서 리뷰 조회
            reviews = await self.fetch_new_reviews_from_api(since, branch_ids)

            if not reviews:
                logger.info("신규 리뷰 없음")
                return PipelineResultDTO(
                    success=True,
                    total_reviews=0,
                    processed_reviews=0,
                    total_branches=0,
                    summaries_generated=0,
                    started_at=started_at,
                    finished_at=datetime.now(),
                )

            # 리뷰 처리
            stats = await self.process_reviews(reviews)

            elapsed = (datetime.now() - started_at).total_seconds()

            return PipelineResultDTO(
                success=True,
                total_reviews=stats.total,
                processed_reviews=stats.processed,
                total_branches=len(stats.branches_updated),
                summaries_generated=0,
                total_duration_seconds=elapsed,
                started_at=started_at,
                finished_at=datetime.now(),
            )

        except Exception as e:
            logger.error(f"증분 파이프라인 오류: {e}")
            return PipelineResultDTO(
                success=False,
                total_reviews=0,
                processed_reviews=0,
                total_branches=0,
                summaries_generated=0,
                error_message=str(e),
                started_at=started_at,
                finished_at=datetime.now(),
            )


# =============================================================================
# KeywordScoreManager (증분 파이프라인용)
# =============================================================================


class KeywordScoreManager:
    """
    키워드 점수 관리자

    증분 업데이트를 위한 키워드 점수 계산 및 관리
    """

    def __init__(self) -> None:
        self.branch_keywords: dict[int, dict[str, dict]] = {}

    def load_from_db(self, branch_id: int, keywords_data: list[dict]) -> None:
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
        self,
        branch_id: int,
        keywords: list[str],
        review_date: datetime | None = None,
    ) -> None:
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

    def apply_decay_to_all(self) -> None:
        """모든 키워드에 시간 감쇠 적용"""
        # 현재는 감쇠 없음 (필요시 구현)
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
    import asyncio

    async def test_batch_pipeline():
        """BatchPipeline 비동기 테스트"""
        print("=== BatchPipeline 비동기 테스트 ===\n")

        pipeline = BatchPipeline(min_reviews=1)

        # DB에서 데이터 로드하여 처리 (branch_ids 지정)
        print("1. DB 로드 테스트")
        try:
            result = await pipeline.run(
                branch_ids=[1234, 5678],
                generate_period_summaries=False,
            )
            print(f"   결과: {result.to_dict()}")
        except Exception as e:
            print(f"   오류: {e}")

        print("\n테스트 완료!")

    async def test_incremental_pipeline():
        """IncrementalPipeline 비동기 테스트"""
        print("\n=== IncrementalPipeline 비동기 테스트 ===\n")

        pipeline = IncrementalPipeline()

        # 테스트 ReviewDTO 생성
        test_reviews = [
            ReviewDTO(
                id=1,
                branch_id=1234,
                content="정말 친절하고 깨끗한 차량이었어요.",
                branch_name="테스트지점",
                rating=4.8,
                created_at=datetime.now(),
                like_count=5,
            ),
        ]

        result = await pipeline.process_reviews(test_reviews)
        print(f"결과: {result.to_dict()}")

    # 테스트 실행
    asyncio.run(test_batch_pipeline())
    asyncio.run(test_incremental_pipeline())
