"""
LLM Provider 추상 클래스
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    """LLM 응답"""

    content: str
    model: str
    tokens_used: int = 0
    success: bool = True
    error: str | None = None


class LLMProvider(ABC):
    """LLM Provider 추상 클래스"""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 300,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """
        텍스트 생성

        Args:
            prompt: 사용자 프롬프트
            system_prompt: 시스템 프롬프트 (선택)
            max_tokens: 최대 토큰 수
            temperature: 생성 온도

        Returns:
            LLMResponse: 생성 결과
        """
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """현재 모델명"""
        pass

    async def async_generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 300,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """텍스트 생성 (비동기). 기본 구현은 sync generate()를 to_thread로 래핑."""
        return await asyncio.to_thread(
            self.generate, prompt, system_prompt, max_tokens, temperature
        )
