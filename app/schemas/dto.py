"""
DTO (Data Transfer Object) 모듈 — Re-export Hub

실제 정의는 도메인별로 분리:
- dto_review.py    : Review, ProcessedReview, BranchReviews 등
- dto_sentiment.py : Sentiment, SentimentStats 등
- dto_summary.py   : Summary 요청/응답, 통계, 승인 등
- dto_pipeline.py  : Pipeline 설정/결과
- dto_analysis.py  : Analysis 페이지, CarModel 등
"""

# --- Review ---
from .dto_review import (
    BranchKeywordsDTO,
    BranchReviewsDTO,
    CleanupResultDTO,
    IncrementalStatsDTO,
    ProcessedReviewDTO,
    ReviewDTO,
)

# --- Sentiment ---
from .dto_sentiment import (
    ReviewSearchResultDTO,
    SentimentDTO,
    SentimentStatsDTO,
)

# --- Summary ---
from .dto_summary import (
    BranchDetailDTO,
    PendingSummaryResultDTO,
    RatingDistributionDTO,
    RatingStatsDTO,
    RegionStatsDTO,
    ReviewOutputDTO,
    SummariesOutputDTO,
    SummaryRequestDTO,
    SummaryResponseDTO,
    SummaryStatsDTO,
    SummaryWithTagsDTO,
    TagSentimentCountDTO,
)

# --- Pipeline ---
from .dto_pipeline import (
    PipelineConfigDTO,
    PipelineResultDTO,
    PipelineStepResultDTO,
)

# --- Analysis & CarModel ---
from .dto_analysis import (
    AnalysisReviewDTO,
    AnalysisReviewListDTO,
    BranchCarModelsDTO,
    BranchOptionDTO,
    CarModelDTO,
    CarModelTagDTO,
    FilterOptionsDTO,
)

__all__ = [
    # Review
    "ReviewDTO",
    "ProcessedReviewDTO",
    "BranchKeywordsDTO",
    "IncrementalStatsDTO",
    "BranchReviewsDTO",
    "CleanupResultDTO",
    # Sentiment
    "SentimentDTO",
    "SentimentStatsDTO",
    "ReviewSearchResultDTO",
    # Summary
    "SummaryRequestDTO",
    "SummaryResponseDTO",
    "SummaryStatsDTO",
    "RegionStatsDTO",
    "RatingDistributionDTO",
    "RatingStatsDTO",
    "SummaryWithTagsDTO",
    "PendingSummaryResultDTO",
    "TagSentimentCountDTO",
    "ReviewOutputDTO",
    "SummariesOutputDTO",
    "BranchDetailDTO",
    # Pipeline
    "PipelineConfigDTO",
    "PipelineStepResultDTO",
    "PipelineResultDTO",
    # Analysis & CarModel
    "CarModelTagDTO",
    "CarModelDTO",
    "BranchCarModelsDTO",
    "BranchOptionDTO",
    "FilterOptionsDTO",
    "AnalysisReviewDTO",
    "AnalysisReviewListDTO",
]
