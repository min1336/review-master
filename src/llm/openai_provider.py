"""
OpenAI GPT Provider
"""
import os
import time
from typing import Optional

from .base import LLMProvider, LLMResponse
from .rate_limiter import RateLimiter


class OpenAIProvider(LLMProvider):
    """
    OpenAI GPT Provider

    GPT-3.5-turbo, GPT-4 등 OpenAI 모델 지원
    """

    def __init__(
        self,
        api_key: str = None,
        model: str = "gpt-3.5-turbo",
        rpm: int = 3500,
        organization: str = None,
        project: str = None
    ):
        """
        Args:
            api_key: OpenAI API 키 (환경변수 OPENAI_API_KEY 사용 가능)
            model: 사용할 모델 (기본값: gpt-3.5-turbo)
            rpm: 분당 최대 요청 수
            organization: OpenAI Organization ID
            project: OpenAI Project ID
        """
        self._api_key = api_key or os.getenv('OPENAI_API_KEY', '')
        self._model = model
        self._client = None
        self._available = None
        self._organization = organization or os.getenv('OPENAI_ORG_ID')
        self._project = project or os.getenv('OPENAI_PROJECT_ID')
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
                project=self._project
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
        temperature: float = 0.7
    ) -> LLMResponse:
        """텍스트 생성"""
        if not self._init_client():
            return LLMResponse(
                content="",
                model=self._model,
                success=False,
                error="OpenAI not available"
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
                temperature=temperature
            )

            content = response.choices[0].message.content.strip()

            # 문장이 잘렸으면 마침표 추가
            if content and not content.endswith(('.', '!', '?', '다', '요', '"')):
                content += '.'

            return LLMResponse(
                content=content,
                model=self._model,
                tokens_used=response.usage.total_tokens if response.usage else 0,
                success=True
            )

        except Exception as e:
            error_msg = str(e)

            # Rate limit 에러 시 재시도
            if '429' in error_msg or 'rate' in error_msg.lower():
                print(f"  ⏳ Rate limit 초과, 60초 대기 후 재시도...")
                time.sleep(60)
                return self.generate(prompt, system_prompt, max_tokens, temperature)

            return LLMResponse(
                content="",
                model=self._model,
                success=False,
                error=error_msg
            )

    def is_available(self) -> bool:
        """Provider 사용 가능 여부"""
        return self._init_client()

    @property
    def model_name(self) -> str:
        """현재 모델명"""
        return self._model
