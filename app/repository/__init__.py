"""
Repository 레이어 - 모든 Repository 일괄 export

Usage:
    from repository import SummaryRepository

    repo = SummaryRepository(client)
    summary = await repo.get_by_branch_id(1)
"""

from __future__ import annotations

from .affiliate_repository import AffiliateRepository, CarModelRepository
from .base import BaseRepository
from .branch_tag_repository import BranchTagRepository
from .review_repository import BranchReviewRepository, ReviewRepository
from .sentiment_repository import SentimentRepository
from .summary_repository import SummaryRepository
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
    "ReviewRepository",
    "BranchReviewRepository",
    # Sentiment
    "SentimentRepository",
    # Affiliates
    "AffiliateRepository",
    "CarModelRepository",
]
