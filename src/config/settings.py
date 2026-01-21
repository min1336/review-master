"""
설정 모듈 - Pydantic Settings
"""
from pydantic_settings import BaseSettings
from typing import Literal
from functools import lru_cache


class Settings(BaseSettings):
    """애플리케이션 설정"""

    # LLM 설정
    llm_provider: Literal["openai", "gemini"] = "openai"

    # OpenAI 설정
    openai_api_key: str = ""
    openai_model: str = "gpt-3.5-turbo"
    openai_rpm: int = 3500

    # Gemini 설정
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-preview-05-20"
    gemini_rpm: int = 1000

    # Supabase 설정
    supabase_url: str = ""
    supabase_key: str = ""

    # 파이프라인 설정
    min_reviews_per_branch: int = 30
    min_review_length: int = 5
    sentiment_threshold: float = 0.45

    # 감정분석 설정
    lexicon_confident_high: float = 0.7
    lexicon_confident_low: float = 0.3
    use_bert: bool = True

    # 성능 설정
    batch_size: int = 1000
    n_jobs: int = -1  # -1: 모든 CPU 코어 사용

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """설정 싱글톤 (캐시됨)"""
    return Settings()
