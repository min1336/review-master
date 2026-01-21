"""
태그 관리 모듈

키워드 → 태그 그룹 분류
- TagMapper: 규칙 기반 매핑 (기존)
- EmbeddingTagClassifier: 임베딩 유사도 기반 분류
- HybridClassifier: ABSA + 임베딩 결합 (권장)
"""

from .mapper import TagMapper
from .embedding_classifier import EmbeddingTagClassifier
from .tag_embeddings import TagEmbeddingManager, TAG_DESCRIPTIONS, TAG_COLORS
from .hybrid_classifier import HybridClassifier

__all__ = [
    'TagMapper',
    'EmbeddingTagClassifier',
    'HybridClassifier',
    'TagEmbeddingManager',
    'TAG_DESCRIPTIONS',
    'TAG_COLORS'
]
