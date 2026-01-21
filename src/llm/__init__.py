"""
LLM 모듈

OpenAI GPT / Google Gemini 기반 요약 생성
Rate Limiting, 프롬프트 관리, 출력 검증
"""
from .base import LLMProvider, LLMResponse
from .openai_provider import OpenAIProvider
from .gemini_provider import GeminiProvider
from .prompts import PromptTemplates, BranchType
from .rate_limiter import RateLimiter
from .validator import validate_summary, validate_and_log

__all__ = [
    'LLMProvider',
    'LLMResponse',
    'OpenAIProvider',
    'GeminiProvider',
    'PromptTemplates',
    'BranchType',
    'RateLimiter',
    'validate_summary',
    'validate_and_log'
]


def get_provider(provider_type: str = None) -> LLMProvider:
    """
    LLM 프로바이더 반환

    Args:
        provider_type: 'openai' 또는 'gemini' (None이면 환경변수 참조)
    """
    import os
    provider = provider_type or os.getenv('LLM_PROVIDER', 'openai')

    if provider == 'gemini':
        return GeminiProvider()
    return OpenAIProvider()
