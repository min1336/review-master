"""
태그 대표 임베딩 관리 (FastEmbed/ONNX 기반)
사전 계산된 임베딩을 저장/로드하여 성능 최적화
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np

from .patterns import TAG_COLORS, TAG_DESCRIPTIONS

logger = logging.getLogger(__name__)


class TagEmbeddingManager:
    """
    태그 임베딩 캐시 관리

    태그 그룹별 대표 임베딩을 계산하고 파일로 캐싱하여
    매번 재계산하지 않도록 함
    """

    DEFAULT_CACHE_PATH = "data/tag_embeddings.npz"

    def __init__(self, model=None, cache_path: str | None = None):
        """
        Args:
            model: FastEmbed TextEmbedding 모델 (지연 로딩 시 None)
            cache_path: 임베딩 캐시 파일 경로
        """
        self.model = model
        self.cache_path = cache_path or self.DEFAULT_CACHE_PATH
        self._embeddings: dict[str, np.ndarray] | None = None

    def compute_embeddings(self) -> dict[str, np.ndarray]:
        """
        각 태그 그룹의 대표 임베딩 계산

        Returns:
            {태그명: 임베딩벡터} 딕셔너리
        """
        if self.model is None:
            msg = "모델이 설정되지 않았습니다. set_model()을 먼저 호출하세요."
            raise RuntimeError(msg)

        logger.info("태그 임베딩 계산 중...")

        embeddings = {}
        descriptions = list(TAG_DESCRIPTIONS.values())
        tags = list(TAG_DESCRIPTIONS.keys())

        # 배치로 한번에 인코딩 (FastEmbed)
        vectors = np.array(list(self.model.embed(descriptions)))

        for tag, vector in zip(tags, vectors, strict=False):
            embeddings[tag] = vector
            logger.debug("  %s: shape=%s", tag, vector.shape)

        logger.info("태그 임베딩 계산 완료: %s개 그룹", len(embeddings))
        return embeddings

    def save(self, embeddings: dict[str, np.ndarray] | None = None) -> bool:
        """
        임베딩을 파일로 저장

        Args:
            embeddings: 저장할 임베딩 (None이면 self._embeddings 사용)

        Returns:
            저장 성공 여부
        """
        embeddings = embeddings or self._embeddings
        if embeddings is None:
            logger.error("저장할 임베딩이 없습니다.")
            return False

        try:
            # 디렉토리 생성
            cache_dir = Path(self.cache_path).parent
            cache_dir.mkdir(parents=True, exist_ok=True)

            # npz 형식으로 저장
            np.savez(self.cache_path, **embeddings)
            logger.info("태그 임베딩 저장 완료: %s", self.cache_path)
            return True

        except Exception as e:
            logger.error("태그 임베딩 저장 실패: %s", e)
            return False

    def load(self) -> dict[str, np.ndarray] | None:
        """
        저장된 임베딩 로드

        Returns:
            {태그명: 임베딩벡터} 딕셔너리 또는 None
        """
        if not os.path.exists(self.cache_path):
            logger.debug("캐시 파일 없음: %s", self.cache_path)
            return None

        try:
            data = np.load(self.cache_path)
            embeddings = {key: data[key] for key in data.files}
            logger.info("태그 임베딩 로드 완료: %s개 그룹", len(embeddings))
            return embeddings

        except Exception as e:
            logger.error("태그 임베딩 로드 실패: %s", e)
            return None

    def get_or_compute(self) -> dict[str, np.ndarray]:
        """
        캐시가 있으면 로드, 없으면 계산 후 저장

        Returns:
            {태그명: 임베딩벡터} 딕셔너리
        """
        # 메모리 캐시 확인
        if self._embeddings is not None:
            return self._embeddings

        # 파일 캐시 확인
        embeddings = self.load()
        if embeddings is not None:
            self._embeddings = embeddings
            return embeddings

        # 새로 계산
        embeddings = self.compute_embeddings()
        self._embeddings = embeddings

        # 파일로 저장
        self.save(embeddings)

        return embeddings

    def get_tag_color(self, tag_name: str) -> str:
        """태그 색상 반환"""
        return TAG_COLORS.get(tag_name, "#6b7280")  # 기본: 회색

