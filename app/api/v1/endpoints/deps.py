from __future__ import annotations

import hmac
import logging
import time
from collections import defaultdict
from typing import TYPE_CHECKING

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.container import ServiceContainer
from repository.database import get_session

logger = logging.getLogger(__name__)


# ============================================================
# Rate Limiter — Public API 보호
# ============================================================


class _RateLimiter:
    """In-memory sliding window rate limiter (단일 프로세스용)"""

    _MAX_KEYS = 10_000  # 메모리 보호: 최대 추적 IP 수

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._check_count = 0

    def check(self, key: str) -> bool:
        now = time.monotonic()
        window_start = now - self.window_seconds
        timestamps = self._requests[key]
        active = [t for t in timestamps if t > window_start]
        if not active:
            self._requests[key] = [now]
            self._maybe_purge(now, window_start)
            return True
        if len(active) >= self.max_requests:
            self._requests[key] = active
            return False
        active.append(now)
        self._requests[key] = active
        return True

    def _maybe_purge(self, now: float, window_start: float) -> None:
        """100회 호출마다 만료된 IP 키 정리"""
        self._check_count += 1
        if self._check_count < 100:
            return
        self._check_count = 0
        expired = [k for k, v in self._requests.items() if not v or v[-1] <= window_start]
        for k in expired:
            del self._requests[k]


_public_api_limiter = _RateLimiter(max_requests=10, window_seconds=60)

if TYPE_CHECKING:
    from domain.pipeline import RealtimePipeline
    from repository.affiliate_repository import AffiliateRepository
    from repository.branch_tag_repository import BranchTagRepository
    from repository.new_review_repository import NewReviewRepository
    from repository.preset_repository import PresetRepository
    from repository.report_job_repository import ReportJobRepository
    from repository.report_repository import ReportRepository
    from repository.review_repository import BranchReviewRepository
    from repository.sentiment_repository import SentimentRepository
    from repository.summary_repository import SummaryRepository
    from repository.tag_repository import CategoryRepository, MappingRepository, TagRepository
    from services.analysis_service import AnalysisService
    from services.carmore_service import CarmoreService
    from services.preset_service import PresetService
    from services.report_job_service import ReportJobService
    from services.report_service import ReportService
    from services.sentiment_service import SentimentService
    from services.summary_service import SummaryService
    from services.sync_job_service import SyncJobService
    from services.sync_service import SyncService
    from services.tag_service import TagService
    from services.upload_job_service import UploadJobService


# ============================================================
# Database Session
# ============================================================


async def get_db_session(
    session: AsyncSession = Depends(get_session),
) -> AsyncSession:
    return session


# ============================================================
# Repositories — Summaries & Reviews
# ============================================================


async def get_summary_repo(
    session: AsyncSession = Depends(get_db_session),
) -> SummaryRepository:
    from repository.summary_repository import SummaryRepository

    return SummaryRepository(session)


async def get_branch_tag_repo(
    session: AsyncSession = Depends(get_db_session),
) -> BranchTagRepository:
    from repository.branch_tag_repository import BranchTagRepository

    return BranchTagRepository(session)


async def get_review_repo(
    session: AsyncSession = Depends(get_db_session),
) -> BranchReviewRepository:
    from repository.review_repository import BranchReviewRepository

    return BranchReviewRepository(session)


# ============================================================
# Repositories — Tags & Sentiment
# ============================================================


async def get_tag_repo(
    session: AsyncSession = Depends(get_db_session),
) -> TagRepository:
    from repository.tag_repository import TagRepository

    return TagRepository(session)


async def get_sentiment_repo(
    session: AsyncSession = Depends(get_db_session),
) -> SentimentRepository:
    from repository.sentiment_repository import SentimentRepository

    return SentimentRepository(session)


# ============================================================
# Repositories — Affiliates & Reports
# ============================================================


async def get_affiliate_repo(
    session: AsyncSession = Depends(get_db_session),
) -> AffiliateRepository:
    from repository.affiliate_repository import AffiliateRepository

    return AffiliateRepository(session)


async def get_category_repo(
    session: AsyncSession = Depends(get_db_session),
) -> CategoryRepository:
    from repository.tag_repository import CategoryRepository

    return CategoryRepository(session)


async def get_mapping_repo(
    session: AsyncSession = Depends(get_db_session),
) -> MappingRepository:
    from repository.tag_repository import MappingRepository

    return MappingRepository(session)


async def get_report_repo(
    session: AsyncSession = Depends(get_db_session),
) -> ReportRepository:
    from repository.report_repository import ReportRepository

    return ReportRepository(session)


async def get_preset_repo(
    session: AsyncSession = Depends(get_db_session),
) -> PresetRepository:
    from repository.preset_repository import PresetRepository

    return PresetRepository(session)


async def get_report_job_repo(
    session: AsyncSession = Depends(get_db_session),
) -> ReportJobRepository:
    from repository.report_job_repository import ReportJobRepository

    return ReportJobRepository(session)


# ============================================================
# Services — Summaries
# ============================================================


async def get_summary_service(
    summary_repo: SummaryRepository = Depends(get_summary_repo),
    branch_tag_repo: BranchTagRepository = Depends(get_branch_tag_repo),
    review_repo: BranchReviewRepository = Depends(get_review_repo),
    sentiment_repo: SentimentRepository = Depends(get_sentiment_repo),
) -> SummaryService:
    from services.summary_service import SummaryService

    return SummaryService(
        summary_repo, branch_tag_repo, review_repo, sentiment_repo,
        athena_client=ServiceContainer.get_athena_client(),
    )


# ============================================================
# Services — Tags & Sentiment
# ============================================================


async def get_tag_service(
    tag_repo: TagRepository = Depends(get_tag_repo),
    branch_tag_repo: BranchTagRepository = Depends(get_branch_tag_repo),
    category_repo: CategoryRepository = Depends(get_category_repo),
    mapping_repo: MappingRepository = Depends(get_mapping_repo),
) -> TagService:
    from services.tag_service import TagService

    return TagService(tag_repo, branch_tag_repo, category_repo, mapping_repo)


async def get_sentiment_service(
    sentiment_repo: SentimentRepository = Depends(get_sentiment_repo),
) -> SentimentService:
    from services.sentiment_service import SentimentService

    return SentimentService(sentiment_repo)


# ============================================================
# Services — External & Analysis
# ============================================================


async def get_carmore_service(
    affiliate_repo: AffiliateRepository = Depends(get_affiliate_repo),
) -> CarmoreService:
    from services.carmore_service import CarmoreService

    return CarmoreService(affiliate_repo)


async def get_new_review_repo(
    session: AsyncSession = Depends(get_db_session),
) -> NewReviewRepository:
    from repository.new_review_repository import NewReviewRepository

    return NewReviewRepository(session)


async def get_analysis_service(
    review_repo: BranchReviewRepository = Depends(get_review_repo),
    summary_repo: SummaryRepository = Depends(get_summary_repo),
    new_review_repo: NewReviewRepository = Depends(get_new_review_repo),
) -> AnalysisService:
    from services.analysis_service import AnalysisService

    return AnalysisService(
        review_repo, summary_repo, ServiceContainer.get_athena_client(),
        new_review_repo=new_review_repo,
    )


async def get_sync_service(
    review_repo: BranchReviewRepository = Depends(get_review_repo),
) -> SyncService:
    from services.sync_service import SyncService

    return SyncService(review_repo, ServiceContainer.get_athena_client())


# ============================================================
# Services — Reports
# ============================================================


# Stateless 서비스 — 모듈 레벨 캐싱 (매 요청마다 재생성 방지)
_pdf_generator = None
_vehicle_analyzer = None


def _get_pdf_generator():
    global _pdf_generator
    if _pdf_generator is None:
        from infrastructure.pdf.generator import PDFGenerator
        _pdf_generator = PDFGenerator()
    return _pdf_generator


def _get_vehicle_analyzer():
    global _vehicle_analyzer
    if _vehicle_analyzer is None:
        from services.vehicle_analyzer import VehicleAnalyzer
        _vehicle_analyzer = VehicleAnalyzer()
    return _vehicle_analyzer


async def get_report_service(
    summary_repo: SummaryRepository = Depends(get_summary_repo),
    review_repo: BranchReviewRepository = Depends(get_review_repo),
    branch_tag_repo: BranchTagRepository = Depends(get_branch_tag_repo),
    report_repo: ReportRepository = Depends(get_report_repo),
    sentiment_repo: SentimentRepository = Depends(get_sentiment_repo),
) -> ReportService:
    from services.report_service import ReportService
    from services.report_cache_service import ReportCacheService
    from services.tag_stats_calculator import TagStatsCalculator
    from services.report_ai_generator import ReportAIGenerator

    cache_service = ReportCacheService(report_repo, review_repo, branch_tag_repo)
    tag_calculator = TagStatsCalculator(branch_tag_repo)
    ai_generator = ReportAIGenerator(summary_repo, review_repo, athena_client=ServiceContainer.get_athena_client())

    return ReportService(
        summary_repo, review_repo, branch_tag_repo,
        report_repo, sentiment_repo,
        _get_pdf_generator(), _get_vehicle_analyzer(),
        cache_service, tag_calculator, ai_generator,
    )


async def get_preset_service(
    preset_repo: PresetRepository = Depends(get_preset_repo),
) -> PresetService:
    from services.preset_service import PresetService

    return PresetService(preset_repo)


async def get_report_job_service(
    job_repo: ReportJobRepository = Depends(get_report_job_repo),
    report_service: ReportService = Depends(get_report_service),
) -> ReportJobService:
    from services.report_job_service import ReportJobService

    return ReportJobService(job_repo, report_service)


# ============================================================
# Services — Sync & Scheduler
# ============================================================


async def get_sync_job_service() -> "SyncJobService":
    from services.sync_job_service import SyncJobService

    return SyncJobService.get_instance()


async def get_upload_job_service() -> "UploadJobService":
    from services.upload_job_service import UploadJobService

    return UploadJobService.get_instance()


async def get_pipeline_job_service():
    from services.pipeline_job_service import PipelineJobService

    return PipelineJobService.get_instance()


async def get_realtime_pipeline() -> "RealtimePipeline":
    return await ServiceContainer.get_realtime_pipeline()



# ============================================================
# Security
# ============================================================


async def require_internal_auth(
    request: Request,
    x_internal_key: str | None = Header(default=None, alias="X-Internal-Key"),
) -> None:
    """내부 API 인증 — X-Internal-Key 헤더 또는 세션 쿠키

    INTERNAL_API_KEY 미설정 시 인증을 건너뛰되 경고 로그를 남긴다.
    """
    from core.config import get_settings

    settings = get_settings()
    expected = settings.internal_api_key.get_secret_value()
    if not expected:
        return

    # 1) X-Internal-Key 헤더 (n8n, 스크립트 등 프로그래밍 방식)
    if x_internal_key and hmac.compare_digest(x_internal_key, expected):
        return

    # 2) 세션 쿠키 (브라우저 대시보드)
    from api.v1.endpoints.auth import SESSION_COOKIE_NAME, validate_session

    if validate_session(request.cookies.get(SESSION_COOKIE_NAME)):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Internal API key required",
    )


async def require_page_auth(request: Request) -> None:
    """페이지 접근 시 세션 쿠키 검증 — 미인증 시 로그인 페이지로 리다이렉트"""
    from core.config import get_settings

    settings = get_settings()
    if not settings.internal_api_key.get_secret_value():
        return

    from api.v1.endpoints.auth import SESSION_COOKIE_NAME, PageAuthRequired, validate_session

    if validate_session(request.cookies.get(SESSION_COOKIE_NAME)):
        return

    raise PageAuthRequired(next_url=request.url.path)


async def require_public_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    from core.config import get_settings

    settings = get_settings()
    expected = settings.public_api_key.get_secret_value()
    if not expected or not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    # Rate limit: 인증 통과 후 IP당 분당 10회 제한
    client_ip = request.client.host if request.client else "unknown"
    if not _public_api_limiter.check(client_ip):
        logger.warning("Rate limit exceeded for IP: %s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )
