"""
OpenAI GPT Provider
"""

from __future__ import annotations

import asyncio
import os
import time

from .base import LLMProvider, LLMResponse
from .rate_limiter import RateLimiter


class OpenAIProvider(LLMProvider):
    """
    OpenAI GPT Provider

    GPT-4 등 OpenAI 모델 지원
    """

    def __init__(
        self,
        api_key: str = None,
        model: str = "gpt-4o-mini",
        rpm: int = 3500,
        organization: str = None,
        project: str = None,
    ):
        """
        Args:
            api_key: OpenAI API 키 (환경변수 OPENAI_API_KEY 사용 가능)
            model: 사용할 모델 (기본값: gpt-4o-mini)
            rpm: 분당 최대 요청 수
            organization: OpenAI Organization ID
            project: OpenAI Project ID
        """
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self._model = model
        self._client = None
        self._available = None
        self._async_client = None
        self._organization = organization or os.getenv("OPENAI_ORG_ID")
        self._project = project or os.getenv("OPENAI_PROJECT_ID")
        self.rate_limiter = RateLimiter(rpm=rpm)

    def _init_client(self) -> bool:
        """클라이언트 초기화 (지연 로딩)"""
        if self._available is not None:
            return self._available

        try:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self._api_key,
                organization=self._organization,
                project=self._project,
            )
            self._available = True
            return True
        except ImportError:
            print("⚠️ openai 패키지 미설치")
            self._available = False
            return False
        except Exception as e:
            print(f"⚠️ OpenAI 초기화 실패: {e}")
            self._available = False
            return False

    def generate(
        self,
        prompt: str,
        system_prompt: str = None,
        max_tokens: int = 300,
        temperature: float = 0.7,
        *,
        max_retries: int = 3,
        _retry_count: int = 0,
    ) -> LLMResponse:
        """텍스트 생성"""
        if not self._init_client():
            return LLMResponse(
                content="",
                model=self._model,
                success=False,
                error="OpenAI not available",
            )

        try:
            self.rate_limiter.wait_if_needed()

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )

            content = response.choices[0].message.content.strip()

            # 문장이 잘렸으면 마침표 추가
            if content and not content.endswith((".", "!", "?", "다", "요", '"')):
                content += "."

            return LLMResponse(
                content=content,
                model=self._model,
                tokens_used=response.usage.total_tokens if response.usage else 0,
                success=True,
            )

        except Exception as e:
            error_msg = str(e)

            # Rate limit 에러 시 재시도
            if "429" in error_msg or "rate" in error_msg.lower():
                if _retry_count < max_retries:
                    wait_time = 60 * (2 ** _retry_count)
                    print(f"  ⏳ Rate limit 초과, {wait_time}초 대기 후 재시도 ({_retry_count + 1}/{max_retries})...")
                    time.sleep(wait_time)
                    return self.generate(
                        prompt, system_prompt, max_tokens, temperature,
                        max_retries=max_retries,
                        _retry_count=_retry_count + 1,
                    )
                return LLMResponse(
                    content="",
                    model=self._model,
                    success=False,
                    error=f"Rate limit exceeded after {max_retries} retries: {error_msg}",
                )

            return LLMResponse(
                content="", model=self._model, success=False, error=error_msg
            )

    def _init_async_client(self) -> bool:
        """비동기 클라이언트 초기화 (지연 로딩)"""
        if self._async_client is not None:
            return True
        try:
            from openai import AsyncOpenAI
            self._async_client = AsyncOpenAI(
                api_key=self._api_key,
                organization=self._organization,
                project=self._project,
            )
            return True
        except ImportError:
            return False
        except Exception as e:
            print(f"⚠️ AsyncOpenAI 초기화 실패: {e}")
            return False

    async def async_generate(
        self,
        prompt: str,
        system_prompt: str = None,
        max_tokens: int = 300,
        temperature: float = 0.7,
        *,
        max_retries: int = 3,
        _retry_count: int = 0,
    ) -> LLMResponse:
        """텍스트 생성 (비동기 - AsyncOpenAI 사용)"""
        if not self._init_async_client():
            return await super().async_generate(
                prompt, system_prompt, max_tokens, temperature
            )
        try:
            await asyncio.to_thread(self.rate_limiter.wait_if_needed)
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = await self._async_client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            content = response.choices[0].message.content.strip()
            if content and not content.endswith((".", "!", "?", "다", "요", '"')):
                content += "."
            return LLMResponse(
                content=content,
                model=self._model,
                tokens_used=response.usage.total_tokens if response.usage else 0,
                success=True,
            )
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "rate" in error_msg.lower():
                if _retry_count < max_retries:
                    wait_time = 60 * (2 ** _retry_count)
                    print(f"  ⏳ Rate limit 초과 (async), {wait_time}초 대기 후 재시도 ({_retry_count + 1}/{max_retries})...")
                    await asyncio.sleep(wait_time)
                    return await self.async_generate(
                        prompt, system_prompt, max_tokens, temperature,
                        max_retries=max_retries,
                        _retry_count=_retry_count + 1,
                    )
                return LLMResponse(
                    content="",
                    model=self._model,
                    success=False,
                    error=f"Rate limit exceeded after {max_retries} retries: {error_msg}",
                )
            return LLMResponse(
                content="", model=self._model, success=False, error=error_msg
            )

    def is_available(self) -> bool:
        """Provider 사용 가능 여부"""
        return self._init_client()

    @property
    def model_name(self) -> str:
        """현재 모델명"""
        return self._model
