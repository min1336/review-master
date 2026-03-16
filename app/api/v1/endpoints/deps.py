"""의존성 주입 팩토리

FastAPI Depends() 체인으로 Repository → Service를 조립.
함수 내부 import는 순환참조 방지용 — 모듈 로드 시점이 아닌 호출 시점에 import.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.container import ServiceContainer
from repository.database import get_session

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from domain.pipeline import RealtimePipeline
    from repository.affiliate_repository import AffiliateRepository
    from repository.branch_tag_repository import BranchTagRepository
    from repository.report_job_repository import ReportJobRepository
    from repository.report_repository import PresetRepository, ReportRepository
    from repository.review_repository import BranchReviewRepository, NewReviewRepository, SentimentRepository
    from repository.summary_repository import SummaryRepository
    from repository.tag_repository import CategoryRepository, MappingRepository, TagRepository
    from services.analysis_service import AnalysisService, CarmoreService
    from services.preset_service import PresetService
    from services.report_job_service import ReportJobService
    from services.report_service import ReportService
    from services.tag_service import SentimentService, TagService
    from services.summary_service import SummaryService
    from services.sync_job_service import SyncJobService
    from services.sync_service import SyncService
    from services.upload_job_service import UploadJobService


# ============================================================
# Database Session
# ============================================================


async def get_db_session(
    session: AsyncSession = Depends(get_session),
) -> AsyncSession:
    return session


# ============================================================
# Repository 팩토리 헬퍼
# ============================================================


def _repo(module: str, cls_name: str):
    """Repository DI 팩토리 생성. 모든 repo는 session 하나만 받는 동일 패턴."""
    async def _factory(session: AsyncSession = Depends(get_db_session)):
        mod = __import__(module, fromlist=[cls_name])
        return getattr(mod, cls_name)(session)
    _factory.__name__ = f"get_{cls_name}"
    _factory.__qualname__ = f"_repo.<locals>.get_{cls_name}"
    return _factory


get_summary_repo = _repo("repository.summary_repository", "SummaryRepository")
get_branch_tag_repo = _repo("repository.branch_tag_repository", "BranchTagRepository")
get_review_repo = _repo("repository.review_repository", "BranchReviewRepository")
get_tag_repo = _repo("repository.tag_repository", "TagRepository")
get_sentiment_repo = _repo("repository.review_repository", "SentimentRepository")
get_affiliate_repo = _repo("repository.affiliate_repository", "AffiliateRepository")
get_category_repo = _repo("repository.tag_repository", "CategoryRepository")
get_mapping_repo = _repo("repository.tag_repository", "MappingRepository")
get_report_repo = _repo("repository.report_repository", "ReportRepository")
get_preset_repo = _repo("repository.report_repository", "PresetRepository")
get_report_job_repo = _repo("repository.report_job_repository", "ReportJobRepository")
get_new_review_repo = _repo("repository.review_repository", "NewReviewRepository")


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
    from services.tag_service import SentimentService

    return SentimentService(sentiment_repo)


# ============================================================
# Services — External & Analysis
# ============================================================


async def get_carmore_service(
    affiliate_repo: AffiliateRepository = Depends(get_affiliate_repo),
) -> CarmoreService:
    from services.analysis_service import CarmoreService

    return CarmoreService(affiliate_repo)


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
