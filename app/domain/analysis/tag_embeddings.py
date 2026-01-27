"""
태그 대표 임베딩 관리
사전 계산된 임베딩을 저장/로드하여 성능 최적화
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


# 태그 그룹별 설명문 (임베딩 계산용)
# 각 태그를 잘 표현하는 키워드와 문맥을 포함
# v2.1: 차량상태 → 차량외관/차량청결, 반납/픽업 + 배차/시간 세분화
TAG_DESCRIPTIONS = {
    "고객응대": (
        "직원 친절 응대 설명 안내 배웅 배려 상담 도움 감사 인사 미소 "
        "고객 만족 인상 표정 웃음"
    ),
    "차량외관": (
        "차량 외관 외부 외형 스크래치 흠집 긁힘 찌그러짐 파손 도색 "
        "페인트 범퍼 휠 타이어 유리 세차"
    ),
    "차량청결": (
        "청결 청소 깨끗 지저분 더러운 냄새 담배 악취 먼지 얼룩 이물질 "
        "쓰레기 실내 내부 시트 바닥 에어컨냄새"
    ),
    "가성비": (
        "가격 저렴 합리적 가성비 할인 비용 요금 싼 싸다 비싸 적정 경제적 부담 렌트비"
    ),
    "위치/접근성": (
        "위치 접근 가까운 공항 역 터미널 교통 편리 거리 도보 이동 찾기 주변 근처"
    ),
    "서비스": (
        "주차 대기실 셔틀버스 시설 화장실 편의 휴게실 음료 커피 "
        "와이파이 충전 예약 확정 변경 취소 앱 사이트 문자 연락 확인 알림 카카오톡"
    ),
    "반납/픽업": "반납 픽업 인수 수령 전달 인계 차량인도 반환 절차 간편 서류",
    "배차/시간": (
        "배차 차종 차량변경 대기 지연 늦게 늦음 빨리 재촉 독촉 시간 "
        "약속시간 출발 도착 기다림 펑크 노쇼"
    ),
    "보험/보장": (
        "보험 보장 면책 면책금 자기부담 자기부담금 완전자차 자차 대인 "
        "대물 사고 보상 보험료 책임 커버 안심 슈퍼 사고접수 사고처리 손해 배상"
    ),
}

# 태그 그룹별 색상 (UI용)
TAG_COLORS = {
    "고객응대": "#10b981",  # 녹색
    "차량외관": "#3b82f6",  # 파란색
    "차량청결": "#0ea5e9",  # 하늘색
    "가성비": "#f59e0b",  # 주황색
    "위치/접근성": "#8b5cf6",  # 보라색
    "서비스": "#ec4899",  # 분홍색
    "반납/픽업": "#06b6d4",  # 청록색
    "배차/시간": "#14b8a6",  # 민트색
    "보험/보장": "#ef4444",  # 빨간색
}


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
            model: SentenceTransformer 모델 (지연 로딩 시 None)
            cache_path: 임베딩 캐시 파일 경로
        """
        self.model = model
        self.cache_path = cache_path or self.DEFAULT_CACHE_PATH
        self._embeddings: dict[str, np.ndarray] | None = None

    def set_model(self, model):
        """모델 설정 (지연 로딩용)"""
        self.model = model

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

        # 배치로 한번에 인코딩
        vectors = self.model.encode(descriptions, convert_to_numpy=True)

        for tag, vector in zip(tags, vectors, strict=False):
            embeddings[tag] = vector
            logger.debug(f"  {tag}: shape={vector.shape}")

        logger.info(f"태그 임베딩 계산 완료: {len(embeddings)}개 그룹")
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
            logger.info(f"태그 임베딩 저장 완료: {self.cache_path}")
            return True

        except Exception as e:
            logger.error(f"태그 임베딩 저장 실패: {e}")
            return False

    def load(self) -> dict[str, np.ndarray] | None:
        """
        저장된 임베딩 로드

        Returns:
            {태그명: 임베딩벡터} 딕셔너리 또는 None
        """
        if not os.path.exists(self.cache_path):
            logger.debug(f"캐시 파일 없음: {self.cache_path}")
            return None

        try:
            data = np.load(self.cache_path)
            embeddings = {key: data[key] for key in data.files}
            logger.info(f"태그 임베딩 로드 완료: {len(embeddings)}개 그룹")
            return embeddings

        except Exception as e:
            logger.error(f"태그 임베딩 로드 실패: {e}")
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

    def get_tag_names(self) -> list:
        """태그 그룹명 목록 반환"""
        return list(TAG_DESCRIPTIONS.keys())

    def get_tag_color(self, tag_name: str) -> str:
        """태그 색상 반환"""
        return TAG_COLORS.get(tag_name, "#6b7280")  # 기본: 회색

    def clear_cache(self) -> bool:
        """캐시 삭제"""
        self._embeddings = None
        if os.path.exists(self.cache_path):
            try:
                os.remove(self.cache_path)
                logger.info(f"캐시 삭제 완료: {self.cache_path}")
                return True
            except Exception as e:
                logger.error(f"캐시 삭제 실패: {e}")
                return False
        return True
