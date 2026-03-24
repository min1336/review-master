"""
LLM 모듈

OpenAI GPT 기반 요약 생성
Rate Limiting, 프롬프트 관리, 출력 검증
"""

from __future__ import annotations

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
    "RateLimiter",
    "validate_summary",
]


def get_provider() -> LLMProvider:
    """LLM 프로바이더 반환"""
    from core.container import ServiceContainer

    return ServiceContainer.get_llm_provider()
