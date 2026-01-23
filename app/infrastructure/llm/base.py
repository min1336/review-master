"""
LLM Provider 추상 클래스
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResponse:
    """LLM 응답"""
    content: str
    model: str
    tokens_used: int = 0
    success: bool = True
    error: Optional[str] = None


class LLMProvider(ABC):
    """LLM Provider 추상 클래스"""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str = None,
        max_tokens: int = 300,
        temperature: float = 0.7
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

    @abstractmethod
    def is_available(self) -> bool:
        """Provider 사용 가능 여부"""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """현재 모델명"""
        pass
