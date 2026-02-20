from __future__ import annotations

import hmac
import logging
from functools import lru_cache
from typing import TYPE_CHECKING
from fastapi import Depends, Header, HTTPException, status
from repository.session import get_client
from supabase import AsyncClient

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from domain.pipeline import RealtimePipeline
    from repository.affiliate_repository import AffiliateRepository
    from repository.branch_tag_repository import BranchTagRepository
    from repository.report_job_repository import ReportJobRepository
    from repository.report_repository import ReportRepository
    from repository.review_repository import BranchReviewRepository
    from repository.sentiment_repository import SentimentRepository
    from repository.summary_repository import SummaryRepository
    from repository.tag_repository import CategoryRepository, MappingRepository, TagRepository
    from services.analysis_service import AnalysisService
    from services.carmore_service import CarmoreService
    from services.report_job_service import ReportJobService
    from services.report_service import ReportService
    from services.sentiment_service import SentimentService
    from services.summary_service import SummaryService
    from services.sync_job_service import SyncJobService
    from services.sync_service import SyncService
    from services.tag_service import TagService


async def get_db_client() -> AsyncClient:
    return await get_client()


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


async def get_category_repo(
    client: AsyncClient = Depends(get_db_client),
) -> CategoryRepository:
    from repository.tag_repository import CategoryRepository

    return CategoryRepository(client)


async def get_mapping_repo(
    client: AsyncClient = Depends(get_db_client),
) -> MappingRepository:
    from repository.tag_repository import MappingRepository

    return MappingRepository(client)


async def get_report_repo(
    client: AsyncClient = Depends(get_db_client),
) -> ReportRepository:
    from repository.report_repository import ReportRepository

    return ReportRepository(client)


async def get_report_job_repo(
    client: AsyncClient = Depends(get_db_client),
) -> ReportJobRepository:
    from repository.report_job_repository import ReportJobRepository

    return ReportJobRepository(client)


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


async def get_carmore_service(
    affiliate_repo: AffiliateRepository = Depends(get_affiliate_repo),
) -> CarmoreService:
    from services.carmore_service import CarmoreService

    return CarmoreService(affiliate_repo)


@lru_cache(maxsize=1)
def _get_athena_client():
    try:
        from core.config import get_settings
        from infrastructure.athena import AthenaClient

        settings = get_settings()
        if settings.aws_access_key_id and settings.athena_output_bucket:
            return AthenaClient()
    except (ImportError, AttributeError, ValueError) as e:
        logger.warning("Athena 클라이언트 초기화 스킵: %s", e)
    return None


async def get_analysis_service(
    review_repo: BranchReviewRepository = Depends(get_review_repo),
    summary_repo: SummaryRepository = Depends(get_summary_repo),
) -> AnalysisService:
    from services.analysis_service import AnalysisService

    return AnalysisService(review_repo, summary_repo, _get_athena_client())


async def get_sync_service(
    review_repo: BranchReviewRepository = Depends(get_review_repo),
) -> SyncService:
    from services.sync_service import SyncService

    return SyncService(review_repo, _get_athena_client())


async def get_report_service(
    summary_repo: SummaryRepository = Depends(get_summary_repo),
    review_repo: BranchReviewRepository = Depends(get_review_repo),
    branch_tag_repo: BranchTagRepository = Depends(get_branch_tag_repo),
    report_repo: ReportRepository = Depends(get_report_repo),
    sentiment_repo: SentimentRepository = Depends(get_sentiment_repo),
) -> ReportService:
    from services.report_service import ReportService
    from services.vehicle_analyzer import VehicleAnalyzer
    from infrastructure.pdf.generator import PDFGenerator

    return ReportService(summary_repo, review_repo, branch_tag_repo, report_repo, sentiment_repo, PDFGenerator(), VehicleAnalyzer())


async def get_report_job_service(
    job_repo: ReportJobRepository = Depends(get_report_job_repo),
    report_service: ReportService = Depends(get_report_service),
) -> ReportJobService:
    from services.report_job_service import ReportJobService

    return ReportJobService(job_repo, report_service)


async def get_sync_job_service() -> "SyncJobService":
    from services.sync_job_service import SyncJobService

    return SyncJobService.get_instance()


async def get_realtime_pipeline() -> "RealtimePipeline":
    from domain.pipeline import RealtimePipeline

    return RealtimePipeline()


async def get_monthly_scheduler_dep():
    from infrastructure.scheduler.monthly_scheduler import get_monthly_scheduler

    return get_monthly_scheduler()


async def get_sync_scheduler_dep():
    from infrastructure.scheduler.sync_scheduler import get_scheduler

    return get_scheduler()


async def require_public_api_key(
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
