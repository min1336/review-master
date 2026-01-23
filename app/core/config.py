"""
환경 설정 모듈

pydantic-settings를 사용하여 .env 파일에서 설정을 로드합니다.
"""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# 환경변수 로드 (프로젝트 루트의 .env)
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(env_path)


class Settings(BaseSettings):
    """애플리케이션 설정"""

    # LLM 설정
    llm_provider: Literal["openai", "gemini"] = "openai"

    # OpenAI 설정
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_rpm: int = 3500

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

    # 성능 설정
    batch_size: int = 1000
    n_jobs: int = -1  # -1: 모든 CPU 코어 사용

    # App
    debug: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤 (캐시됨)"""
    return Settings()
