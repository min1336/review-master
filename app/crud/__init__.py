"""
Repository 레이어 - 모든 Repository 일괄 export

Usage:
    from repositories import UnitOfWork, SummaryRepository

    # UnitOfWork 사용 (권장)
    uow = UnitOfWork(client)
    summary = await uow.summaries.get_by_branch_id(1)

    # 개별 Repository 사용
    repo = SummaryRepository(client)
    summary = await repo.get_by_branch_id(1)
"""

from .base import BaseRepository
from .unit_of_work import UnitOfWork
from .summary_crud import SummaryRepository
from .branch_tag_crud import BranchTagRepository
from .tag_crud import TagRepository, CategoryRepository, MappingRepository
from .review_crud import ReviewRepository, BranchReviewRepository
from .sentiment_crud import SentimentRepository
from .affiliate_crud import AffiliateRepository, CarModelRepository

__all__ = [
    # Base
    "BaseRepository",
    "UnitOfWork",
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
