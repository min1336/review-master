"""
분석 모듈

- 키워드 추출 (Kiwi 기반)
- 태그 분류 (HybridClassifier: ABSA + 임베딩)
- ABSA (Aspect-Based Sentiment Analysis)
- 청킹 (절 단위 분리)
- 통합 감정 분석 (UnifiedSentimentAnalyzer)
"""

from __future__ import annotations

from .absa import RuleBasedABSA
from .aggregator import KeywordAggregator
from .chunker import ClauseChunker
from .extractor import KeywordExtractor
from .hybrid_classifier import HybridClassifier
from .patterns import (
    ASPECT_KEYWORDS,
    DOUBLE_NEGATION_PATTERNS,
    DOUBLE_NEGATION_REGEX,
    GENERAL_POSITIVE_KEYWORDS,
    NEGATIVE_PATTERNS,
    NEGATIVE_REGEX,
    POSITIVE_EXCEPTION_REGEX,
    POSITIVE_EXCEPTIONS,
    POSITIVE_PATTERNS,
    POSITIVE_REGEX,
    RULE_BASED_TAG_MAPPING,
    TAG_COLORS,
    TAG_DESCRIPTIONS,
    TAG_REGISTRY,
    extract_stem,
)
from .sentiment_core import (
    check_double_negation,
    count_sentiment_matches,
    detect_keyword_sentiment,
    detect_keyword_sentiment_with_context,
)
from .sentiment_utils import SentimentResult, UnifiedSentimentAnalyzer
from .tag_embeddings import TagEmbeddingManager

__all__ = [
    # Keywords
    "KeywordExtractor",
    "KeywordAggregator",
    # Tags
    "HybridClassifier",
    "TagEmbeddingManager",
    "TAG_DESCRIPTIONS",
    "TAG_COLORS",
    # Chunking
    "ClauseChunker",
    # ABSA
    "RuleBasedABSA",
    # Unified Sentiment
    "UnifiedSentimentAnalyzer",
    "SentimentResult",
    # Registry
    "TAG_REGISTRY",
    "ASPECT_KEYWORDS",
    # Patterns
    "NEGATIVE_PATTERNS",
    "POSITIVE_PATTERNS",
    "POSITIVE_EXCEPTIONS",
    "DOUBLE_NEGATION_PATTERNS",
    "GENERAL_POSITIVE_KEYWORDS",
    "RULE_BASED_TAG_MAPPING",
    "NEGATIVE_REGEX",
    "POSITIVE_REGEX",
    "POSITIVE_EXCEPTION_REGEX",
    "DOUBLE_NEGATION_REGEX",
    # Sentiment Core
    "detect_keyword_sentiment",
    "detect_keyword_sentiment_with_context",
    "check_double_negation",
    "count_sentiment_matches",
    # Utils
    "extract_stem",
]

