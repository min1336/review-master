"""
Repository 레이어 - 모든 Repository 일괄 export

Usage:
    from repository import SummaryRepository

    repo = SummaryRepository(client)
    summary = await repo.get_by_branch_id(1)
"""

from __future__ import annotations

from .affiliate_repository import AffiliateRepository, CarModelCatalogRepository
from .base import BaseRepository
from .branch_tag_repository import BranchTagRepository
from .report_job_repository import ReportJobRepository
from .report_repository import PresetRepository, ReportRepository
from .review_repository import BranchReviewRepository, NewReviewRepository, SentimentRepository
from .summary_repository import SummaryRepository
from .sync_metadata_repository import SyncMetadataRepository
from .tag_repository import CategoryRepository, MappingRepository, TagRepository

__all__ = [
    # Base
    "BaseRepository",
    # Summary
    "SummaryRepository",
    # Tags
    "TagRepository",
    "CategoryRepository",
    "MappingRepository",
    "BranchTagRepository",
    # Reviews
    "BranchReviewRepository",
    # Sentiment
    "SentimentRepository",
    # New Reviews
    "NewReviewRepository",
    # Presets
    "PresetRepository",
    # Affiliates
    "AffiliateRepository",
    "CarModelCatalogRepository",
    # Reports
    "ReportRepository",
    "ReportJobRepository",
    # Sync
    "SyncMetadataRepository",
]
