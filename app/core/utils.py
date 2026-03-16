"""공통 유틸리티 (TTL 캐시, 시간 감쇠)"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from math import exp
from typing import Any

from core.constants import DECAY_LAMBDA


# ── TTL Cache ────────────────────────────────────────────────

class TTLCache:
    """간단한 TTL 기반 인메모리 캐시

    Args:
        ttl_seconds: 캐시 항목 유효 시간 (초). 기본 300초(5분).
    """

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.monotonic() + self._ttl, value)

    def invalidate(self, key: str | None = None) -> None:
        if key is None:
            self._store.clear()
        else:
            self._store.pop(key, None)


# ── Decay ────────────────────────────────────────────────────

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
    if review_date.tzinfo is None:
        review_date = review_date.replace(tzinfo=timezone.utc)
    if reference_date.tzinfo is None:
        reference_date = reference_date.replace(tzinfo=timezone.utc)
    days_ago = max(0, (reference_date - review_date).days)
    return exp(-DECAY_LAMBDA * days_ago)
