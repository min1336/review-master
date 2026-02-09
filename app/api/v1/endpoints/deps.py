"""
FastAPI 의존성 주입 컨테이너

모든 Repository와 Service의 의존성을 관리합니다.

Usage:
    from api.deps import get_summary_service

    @router.get("/summaries")
    async def api_summaries(
        service: SummaryService = Depends(get_summary_service),
    ):
        return await service.get_summaries()
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import Depends, Header, HTTPException, status
from repository.session import get_client
from supabase import AsyncClient

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from repository.affiliate_repository import AffiliateRepository
    from repository.branch_tag_repository import BranchTagRepository
    from repository.report_job_repository import ReportJobRepository
    from repository.report_repository import ReportRepository
    from repository.review_repository import BranchReviewRepository
    from repository.sentiment_repository import SentimentRepository
    from repository.summary_repository import SummaryRepository
    from repository.tag_repository import TagRepository
    from services.analysis_service import AnalysisService
    from services.carmore_service import CarmoreService
    from services.report_job_service import ReportJobService
    from services.report_service import ReportService
    from services.sentiment_service import SentimentService
    from services.summary_service import SummaryService
    from services.sync_service import SyncService
    from services.tag_service import TagService

# ============================================================
# Database Client
# ============================================================


async def get_db_client() -> AsyncClient:
    """Supabase AsyncClient 의존성"""
    return await get_client()


# Alias for direct client access
async def get_supabase_client() -> AsyncClient:
    """Supabase AsyncClient 의존성 (alias)"""
    return await get_client()


# ============================================================
# Repositories
# ============================================================


async def get_summary_repo(
    client: AsyncClient = Depends(get_db_client),
) -> SummaryRepository:
    from repository.summary_repository import SummaryRepository

    return SummaryRepository(client)


async def get_branch_tag_repo(
    client: AsyncClient = Depends(get_db_client),
) -> BranchTagRepository:
    from repository.branch_tag_repository import BranchTagRepository

    return BranchTagRepository(client)


async def get_review_repo(
    client: AsyncClient = Depends(get_db_client),
) -> BranchReviewRepository:
    from repository.review_repository import BranchReviewRepository

    return BranchReviewRepository(client)


async def get_tag_repo(
    client: AsyncClient = Depends(get_db_client),
) -> TagRepository:
    from repository.tag_repository import TagRepository

    return TagRepository(client)


async def get_sentiment_repo(
    client: AsyncClient = Depends(get_db_client),
) -> SentimentRepository:
    from repository.sentiment_repository import SentimentRepository

    return SentimentRepository(client)


async def get_affiliate_repo(
    client: AsyncClient = Depends(get_db_client),
) -> AffiliateRepository:
    from repository.affiliate_repository import AffiliateRepository

    return AffiliateRepository(client)


# ============================================================
# Services
# ============================================================


async def get_summary_service(
    summary_repo: SummaryRepository = Depends(get_summary_repo),
    branch_tag_repo: BranchTagRepository = Depends(get_branch_tag_repo),
    review_repo: BranchReviewRepository = Depends(get_review_repo),
    sentiment_repo: SentimentRepository = Depends(get_sentiment_repo),
) -> SummaryService:
    from services.summary_service import SummaryService

    return SummaryService(summary_repo, branch_tag_repo, review_repo, sentiment_repo)


async def get_tag_service(
    tag_repo: TagRepository = Depends(get_tag_repo),
    branch_tag_repo: BranchTagRepository = Depends(get_branch_tag_repo),
) -> TagService:
    from services.tag_service import TagService

    return TagService(tag_repo, branch_tag_repo)


async def get_sentiment_service(
    sentiment_repo: SentimentRepository = Depends(get_sentiment_repo),
    review_repo: BranchReviewRepository = Depends(get_review_repo),
) -> SentimentService:
    from services.sentiment_service import SentimentService

    return SentimentService(sentiment_repo, review_repo)


async def get_carmore_service(
    affiliate_repo: AffiliateRepository = Depends(get_affiliate_repo),
) -> CarmoreService:
    from services.carmore_service import CarmoreService

    return CarmoreService(affiliate_repo)


async def get_analysis_service(
    review_repo: BranchReviewRepository = Depends(get_review_repo),
    summary_repo: SummaryRepository = Depends(get_summary_repo),
) -> AnalysisService:
    from services.analysis_service import AnalysisService

    # Athena 클라이언트 초기화 (설정이 있는 경우에만)
    athena_client = None
    try:
        from core.config import get_settings
        from infrastructure.athena import AthenaClient

        settings = get_settings()
        if settings.aws_access_key_id and settings.athena_output_bucket:
            athena_client = AthenaClient()
    except Exception as e:
        logger.debug(f"Athena 클라이언트 초기화 스킵: {e}")

    return AnalysisService(review_repo, summary_repo, athena_client)


async def get_sync_service(
    review_repo: BranchReviewRepository = Depends(get_review_repo),
) -> SyncService:
    from services.sync_service import SyncService

    # Athena 클라이언트 초기화 (설정이 있는 경우에만)
    athena_client = None
    try:
        from core.config import get_settings
        from infrastructure.athena import AthenaClient

        settings = get_settings()
        if settings.aws_access_key_id and settings.athena_output_bucket:
            athena_client = AthenaClient()
    except Exception as e:
        logger.debug(f"Athena 클라이언트 초기화 스킵: {e}")

    return SyncService(review_repo, athena_client)


async def get_report_repo(
    client: AsyncClient = Depends(get_db_client),
) -> "ReportRepository":
    from repository.report_repository import ReportRepository

    return ReportRepository(client)


async def get_report_service(
    summary_repo: SummaryRepository = Depends(get_summary_repo),
    review_repo: BranchReviewRepository = Depends(get_review_repo),
    branch_tag_repo: BranchTagRepository = Depends(get_branch_tag_repo),
    report_repo: "ReportRepository" = Depends(get_report_repo),
    sentiment_repo: SentimentRepository = Depends(get_sentiment_repo),
) -> ReportService:
    from services.report_service import ReportService

    return ReportService(summary_repo, review_repo, branch_tag_repo, report_repo, sentiment_repo)


async def get_report_job_repo(
    client: AsyncClient = Depends(get_db_client),
) -> "ReportJobRepository":
    from repository.report_job_repository import ReportJobRepository

    return ReportJobRepository(client)


async def get_report_job_service(
    job_repo: "ReportJobRepository" = Depends(get_report_job_repo),
    report_service: ReportService = Depends(get_report_service),
) -> "ReportJobService":
    from services.report_job_service import ReportJobService

    return ReportJobService(job_repo, report_service)


# ============================================================
# Auth (Public API)
# ============================================================


async def require_public_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Public API Key 검증"""
    from core.config import get_settings

    settings = get_settings()
    expected = settings.public_api_key.get_secret_value()
    if not expected or not x_api_key or x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


# ============================================================
# Scheduler Settings
# ============================================================


async def get_scheduler_settings_repo(
    client: AsyncClient = Depends(get_db_client),
):
    from repository.scheduler_settings_repository import SchedulerSettingsRepository

    return SchedulerSettingsRepository(client)


async def get_scheduler_settings_service(
    settings_repo=Depends(get_scheduler_settings_repo),
):
    from services.scheduler_settings_service import SchedulerSettingsService

    return SchedulerSettingsService(settings_repo)

