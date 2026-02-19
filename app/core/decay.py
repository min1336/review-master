"""
태그 시간 감쇠 유틸리티

최근 리뷰일수록 높은 가중치를 부여하는 지수 감쇠 함수를 제공합니다.

반감기 참고:
    lambda=0.01 → 반감기 약 69일 (ln(2) / 0.01)
    - 30일 전: ~0.741
    - 69일 전: ~0.500
    - 180일 전: ~0.165
    - 365일 전: ~0.026
"""

from __future__ import annotations

from datetime import datetime, timezone
from math import exp

from core.constants import DECAY_LAMBDA


def compute_decay(review_date: datetime | None, reference_date: datetime) -> float:
    """
    리뷰 날짜 기반 지수 감쇠 계수 반환.

    Args:
        review_date: 리뷰 작성일 (None이면 최고 가중치 1.0 반환)
        reference_date: 기준일 (보통 오늘)

    Returns:
        0.0 ~ 1.0 범위의 감쇠 계수
    """
    if review_date is None:
        return 1.0
    # timezone-naive datetime은 UTC로 간주 (CSV 등 외부 소스 호환)
    if review_date.tzinfo is None:
        review_date = review_date.replace(tzinfo=timezone.utc)
    if reference_date.tzinfo is None:
        reference_date = reference_date.replace(tzinfo=timezone.utc)
    days_ago = max(0, (reference_date - review_date).days)
    return exp(-DECAY_LAMBDA * days_ago)
