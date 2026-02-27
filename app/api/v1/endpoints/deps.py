from __future__ import annotations

import hmac
import logging
from functools import lru_cache
from typing import TYPE_CHECKING

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from repository.database import get_session

logger = logging.getLogger(__name__)

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
        athena_client=_get_athena_client(),
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
        review_repo, summary_repo, _get_athena_client(),
        new_review_repo=new_review_repo,
    )


async def get_sync_service(
    review_repo: BranchReviewRepository = Depends(get_review_repo),
) -> SyncService:
    from services.sync_service import SyncService

    return SyncService(review_repo, _get_athena_client())


# ============================================================
# Services — Reports
# ============================================================


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
    from services.vehicle_analyzer import VehicleAnalyzer
    from infrastructure.pdf.generator import PDFGenerator

    cache_service = ReportCacheService(report_repo, review_repo, branch_tag_repo)
    tag_calculator = TagStatsCalculator(branch_tag_repo)
    ai_generator = ReportAIGenerator(summary_repo, review_repo, athena_client=_get_athena_client())

    return ReportService(
        summary_repo, review_repo, branch_tag_repo,
        report_repo, sentiment_repo,
        PDFGenerator(), VehicleAnalyzer(),
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
    from domain.pipeline import RealtimePipeline

    return RealtimePipeline()



# ============================================================
# Security
# ============================================================


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
