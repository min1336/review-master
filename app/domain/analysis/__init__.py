"""
분석 모듈

- 키워드 추출 (MeCab 기반)
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
    extract_stem,
    get_tag_for_keyword,
    is_negative_keyword,
)
from .sentiment_utils import SentimentResult, UnifiedSentimentAnalyzer
from .tag_embeddings import TAG_COLORS, TAG_DESCRIPTIONS, TagEmbeddingManager

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
    # Utils
    "extract_stem",
    "is_negative_keyword",
    "get_tag_for_keyword",
]

