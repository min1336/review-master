"""
LLM 모듈

OpenAI GPT 기반 요약 생성
Rate Limiting, 프롬프트 관리, 출력 검증
"""

from __future__ import annotations

from core.config import BranchType

from .base import LLMProvider, LLMResponse
from .openai_provider import OpenAIProvider
from .prompts import OperationalSummaryPromptBuilder, SummaryPromptBuilder
from .rate_limiter import RateLimiter
from .validator import validate_summary

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "OpenAIProvider",
    "SummaryPromptBuilder",
    "OperationalSummaryPromptBuilder",
    "BranchType",
    "RateLimiter",
    "validate_summary",
]


def get_provider(provider_type: str = None) -> LLMProvider:
    """
    LLM 프로바이더 반환

    Args:
        provider_type: 'openai' (기본값)
    """
    from core.config import get_settings

    settings = get_settings()
    return OpenAIProvider(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_model,
        rpm=settings.openai_rpm,
    )
