"""
분석 모듈

- 키워드 추출 (MeCab 기반)
- 태그 분류 (임베딩/규칙 기반)
- ABSA (Aspect-Based Sentiment Analysis)
- 청킹 (절 단위 분리)
"""
from .extractor import KeywordExtractor
from .aggregator import KeywordAggregator
from .weight import WeightCalculator, KeywordScoreManager
from .mapper import TagMapper
from .embedding_classifier import EmbeddingTagClassifier
from .hybrid_classifier import HybridClassifier
from .tag_embeddings import TagEmbeddingManager, TAG_DESCRIPTIONS, TAG_COLORS
from .chunker import ClauseChunker
from .absa import RuleBasedABSA

__all__ = [
    # Keywords
    'KeywordExtractor',
    'KeywordAggregator',
    'WeightCalculator',
    'KeywordScoreManager',
    # Tags
    'TagMapper',
    'EmbeddingTagClassifier',
    'HybridClassifier',
    'TagEmbeddingManager',
    'TAG_DESCRIPTIONS',
    'TAG_COLORS',
    # Chunking
    'ClauseChunker',
    # ABSA
    'RuleBasedABSA',
]
