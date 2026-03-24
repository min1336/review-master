"""
PDF 캐싱 전략 인터페이스

NullCache(캐싱 없음)와 InMemoryPdfCache(인메모리 TTL 캐시)를 제공합니다.
추후 Supabase Storage 등 외부 캐시를 추가할 수 있도록
인터페이스를 미리 정의합니다.
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod


class PDFCacheStrategy(ABC):
    """PDF 캐시 전략 인터페이스"""

    @abstractmethod
    def get(self, key: str) -> bytes | None:
        """캐시에서 PDF 바이트를 조회. 없으면 None."""

    @abstractmethod
    def put(self, key: str, data: bytes) -> None:
        """PDF 바이트를 캐시에 저장."""

    @abstractmethod
    def invalidate(self, key: str) -> None:
        """특정 키의 캐시를 무효화."""


class NullCache(PDFCacheStrategy):
    """캐싱 없음 (기본 구현)"""

    def get(self, key: str) -> bytes | None:
        return None

    def put(self, key: str, data: bytes) -> None:
        pass

    def invalidate(self, key: str) -> None:
        pass


class InMemoryPdfCache(PDFCacheStrategy):
    """인메모리 TTL 캐시 (LRU eviction)

    Args:
        ttl: 캐시 유효 시간 (초, 기본 600)
        max_size: 최대 항목 수 (기본 50)
    """

    def __init__(self, ttl: float = 600.0, max_size: int = 50) -> None:
        self._ttl = ttl
        self._max_size = max_size
        # key -> (timestamp, data)
        self._store: dict[str, tuple[float, bytes]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> bytes | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            timestamp, data = entry
            if time.monotonic() - timestamp > self._ttl:
                del self._store[key]
                return None
            return data

    def put(self, key: str, data: bytes) -> None:
        with self._lock:
            if key in self._store:
                del self._store[key]
            elif len(self._store) >= self._max_size:
                # LRU: 가장 오래된 항목 제거 (삽입 순서 기준)
                oldest_key = next(iter(self._store))
                del self._store[oldest_key]
            self._store[key] = (time.monotonic(), data)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)
