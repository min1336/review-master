"""
LLM 모듈

OpenAI GPT 기반 요약 생성
Rate Limiting, 프롬프트 관리, 출력 검증
"""
from .base import LLMProvider, LLMResponse
from .openai_provider import OpenAIProvider
from .prompts import SummaryPromptBuilder
from app.core.config import BranchType
from .rate_limiter import RateLimiter
from .validator import validate_summary, validate_and_log

__all__ = [
    'LLMProvider',
    'LLMResponse',
    'OpenAIProvider',
    'SummaryPromptBuilder',
    'BranchType',
    'RateLimiter',
    'validate_summary',
    'validate_and_log'
]


def get_provider(provider_type: str = None) -> LLMProvider:
    """
    LLM 프로바이더 반환

    Args:
        provider_type: 'openai' (기본값)
    """
    return OpenAIProvider()
