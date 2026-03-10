"""TTL 기반 인메모리 캐시"""

from __future__ import annotations

import time
from typing import Any


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
