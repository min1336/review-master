"""
Core 모듈 - 설정 및 데이터베이스 연결
"""

from __future__ import annotations

from .config import Settings, get_settings

__all__ = [
    "Settings",
    "get_settings",
]
