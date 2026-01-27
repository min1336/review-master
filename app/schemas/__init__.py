"""
Pydantic 스키마 모듈
"""

from __future__ import annotations

from .common import CleanupRequest, ErrorResponse, SuccessResponse
from .dto import (
    BranchDetailDTO,
    BranchReviewsDTO,
    CleanupResultDTO,
    KeywordSentimentDTO,
    PendingSummaryResultDTO,
    PipelineConfigDTO,
    PipelineResultDTO,
    PipelineStepResultDTO,
    RatingDistributionDTO,
    RatingStatsDTO,
    RegionStatsDTO,
    ReviewDTO,
    ReviewOutputDTO,
    ReviewSearchResultDTO,
    SentimentDTO,
    SentimentStatsDTO,
    SummariesOutputDTO,
    SummaryRequestDTO,
    SummaryResponseDTO,
    SummaryStatsDTO,
    SummaryWithTagsDTO,
    TagAnalysisResultDTO,
    TagGroupDTO,
    TagSentimentCountDTO,
)
from .entities import (
    Affiliate,
    BranchTag,
    Category,
    KeywordMapping,
    Review,
    SentimentStats,
    Summary,
    Tag,
)
from .summary import RegenerateRequest, StatusUpdate, SummaryUpdate
from .tag import (
    BulkMappingRequest,
    CategoryCreate,
    CategoryUpdate,
    KeywordMappingCreate,
    TagAnalysisRequest,
    TagCreate,
    TagUpdate,
)

__all__ = [
    # common
    "CleanupRequest",
    "ErrorResponse",
    "SuccessResponse",
    # dto
    "BranchDetailDTO",
    "BranchReviewsDTO",
    "CleanupResultDTO",
    "KeywordSentimentDTO",
    "PendingSummaryResultDTO",
    "PipelineConfigDTO",
    "PipelineResultDTO",
    "PipelineStepResultDTO",
    "RatingDistributionDTO",
    "RatingStatsDTO",
    "RegionStatsDTO",
    "ReviewDTO",
    "ReviewOutputDTO",
    "ReviewSearchResultDTO",
    "SentimentDTO",
    "SentimentStatsDTO",
    "SummariesOutputDTO",
    "SummaryRequestDTO",
    "SummaryResponseDTO",
    "SummaryStatsDTO",
    "SummaryWithTagsDTO",
    "TagAnalysisResultDTO",
    "TagGroupDTO",
    "TagSentimentCountDTO",
    # entities
    "Affiliate",
    "BranchTag",
    "Category",
    "KeywordMapping",
    "Review",
    "SentimentStats",
    "Summary",
    "Tag",
    # summary
    "RegenerateRequest",
    "StatusUpdate",
    "SummaryUpdate",
    # tag
    "BulkMappingRequest",
    "CategoryCreate",
    "CategoryUpdate",
    "KeywordMappingCreate",
    "TagAnalysisRequest",
    "TagCreate",
    "TagUpdate",
]
