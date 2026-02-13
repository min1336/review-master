"""
PDF 캐싱 전략 인터페이스

현재는 NullCache(캐싱 없음)만 제공합니다.
추후 Supabase Storage 등 외부 캐시를 추가할 수 있도록
인터페이스를 미리 정의합니다.
"""

from __future__ import annotations

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
