"""
Google Gemini Provider
"""
import os
import time
from typing import Optional

from .base import LLMProvider, LLMResponse
from .rate_limiter import RateLimiter


class GeminiProvider(LLMProvider):
    """
    Google Gemini Provider

    Gemini 2.5 Flash 등 Google AI 모델 지원
    """

    def __init__(
        self,
        api_key: str = None,
        model: str = "gemini-2.5-flash-preview-05-20",
        rpm: int = 1000
    ):
        """
        Args:
            api_key: Gemini API 키 (환경변수 GEMINI_API_KEY 사용 가능)
            model: 사용할 모델 (기본값: gemini-2.5-flash-preview-05-20)
            rpm: 분당 최대 요청 수
        """
        self._api_key = api_key or os.getenv('GEMINI_API_KEY', '')
        self._model_name = model
        self._model = None
        self._available = None
        self.rate_limiter = RateLimiter(rpm=rpm)

    def _init_client(self) -> bool:
        """클라이언트 초기화 (지연 로딩)"""
        if self._available is not None:
            return self._available

        try:
            import google.generativeai as genai
            genai.configure(api_key=self._api_key)
            self._model = genai.GenerativeModel(self._model_name)
            self._available = True
            return True
        except ImportError:
            print("⚠️ google-generativeai 패키지 미설치")
            self._available = False
            return False
        except Exception as e:
            print(f"⚠️ Gemini 초기화 실패: {e}")
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
                model=self._model_name,
                success=False,
                error="Gemini not available"
            )

        try:
            self.rate_limiter.wait_if_needed()

            # Gemini는 system prompt를 user prompt에 포함
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"

            response = self._model.generate_content(full_prompt)
            content = response.text.strip()

            # 문장이 잘렸으면 마침표 추가
            if content and not content.endswith(('.', '!', '?', '다', '요', '"')):
                content += '.'

            return LLMResponse(
                content=content,
                model=self._model_name,
                success=True
            )

        except Exception as e:
            error_msg = str(e)

            # Rate limit 에러 시 재시도
            if '429' in error_msg or 'rate' in error_msg.lower() or 'quota' in error_msg.lower():
                print(f"  ⏳ Rate limit 초과, 60초 대기 후 재시도...")
                time.sleep(60)
                return self.generate(prompt, system_prompt, max_tokens, temperature)

            return LLMResponse(
                content="",
                model=self._model_name,
                success=False,
                error=error_msg
            )

    def is_available(self) -> bool:
        """Provider 사용 가능 여부"""
        return self._init_client()

    @property
    def model_name(self) -> str:
        """현재 모델명"""
        return self._model_name
