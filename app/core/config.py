"""
환경 설정 모듈

pydantic-settings를 사용하여 .env 파일에서 설정을 로드합니다.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from urllib.parse import quote_plus

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# 프로젝트 루트 디렉토리 (app의 상위 디렉토리)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """애플리케이션 설정"""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM 설정
    llm_provider: Literal["openai"] = "openai"

    # OpenAI 설정
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-4o-mini"
    openai_rpm: int = 3500
    openai_org_id: str = ""
    openai_project_id: str = ""

    # Database 설정 (SQLAlchemy + asyncpg)
    database_url: str = ""  # postgresql+asyncpg://user:pass@host:port/dbname
    database_user: str = ""
    database_password: SecretStr = SecretStr("")
    database_host: str = ""
    database_port: str = "5432"
    database_name: str = "postgres"

    def get_database_url(self) -> str:
        """DATABASE_URL 우선, 없으면 개별 필드로 조합"""
        if self.database_url:
            return self.database_url
        if self.database_host and self.database_user:
            password = quote_plus(self.database_password.get_secret_value())
            return (
                f"postgresql+asyncpg://{self.database_user}:{password}"
                f"@{self.database_host}:{self.database_port}/{self.database_name}"
            )
        return ""

    # 파이프라인 설정
    sentiment_threshold: float = 0.45

    # 감정분석 설정
    lexicon_confident_high: float = 0.7
    lexicon_confident_low: float = 0.3

    # 성능 설정
    batch_size: int = 1000
    n_jobs: int = -1  # -1: 모든 CPU 코어 사용

    # App
    debug: bool = False

    # API Routing (환경별 분기)
    # 로컬: /api, 프로덕션(Nginx): /review/api
    api_prefix: str = "/api"

    # CORS 허용 도메인 (쉼표 구분 문자열, 예: "https://a.com,https://b.com")
    cors_origins: str = ""

    # AWS Athena 설정
    aws_access_key_id: str = ""
    aws_secret_access_key: SecretStr = SecretStr("")
    aws_region: str = "ap-northeast-2"
    athena_database: str = "carmore"
    athena_output_bucket: str = ""

    # n8n 웹훅 설정
    # 로컬(기본): /webhook-test (동기 응답), Docker/실서버: N8N_TEST_MODE=false → /webhook
    n8n_test_mode: bool = True
    n8n_api_key: SecretStr = SecretStr("")
    n8n_base_url: str = "https://n8n-cloud.carmore.kr"
    slack_bot_base_url: str = "http://slack-bot:8080"

    # Carmore 관리자 URL (로컬: dev-admin, 실서버: admin)
    carmore_admin_url: str = "https://dev-admin.carmore.kr"

    # 스케줄러 설정
    sync_hour: int = 6  # 동기화 실행 시간 (시)
    sync_minute: int = 0  # 동기화 실행 시간 (분)


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤 (캐시됨)"""
    return Settings()


class BranchType(Enum):
    """지점 유형"""

    AIRPORT = "airport"
    CITY = "city"
    TOURIST = "tourist"
    DEFAULT = "default"


REGION_CONFIG = {
    "airport_keywords": [
        "공항",
        "인천공항",
        "김포공항",
        "제주공항",
        "김해공항",
        "대구공항",
    ],
    "tourist_keywords": ["제주", "부산", "강릉", "속초", "여수", "경주", "전주"],
    "region_emphasis": {
        "제주": ["여행", "드라이브", "관광", "해안도로", "렌트"],
        "제주공항": ["픽업", "셔틀", "관광", "드라이브"],
        "부산": ["해운대", "관광", "여행"],
        "인천": ["공항", "픽업", "셔틀", "국제선"],
        "인천공항": ["픽업", "셔틀", "국제선", "심야"],
        "김포": ["공항", "픽업", "셔틀", "국내선"],
        "김포공항": ["픽업", "셔틀", "국내선", "빠른"],
        "김해": ["공항", "픽업", "부산권"],
        "김해공항": ["픽업", "셔틀", "부산권"],
        "대구공항": ["픽업", "대구권"],
        "강남": ["접근성", "주차", "비즈니스"],
        "서울": ["접근성", "주차", "교통"],
    },
    "regions": [
        "인천공항",
        "김포공항",
        "제주공항",
        "김해공항",
        "대구공항",
        "제주",
        "부산",
        "인천",
        "김포",
        "김해",
        "대구",
        "광주",
        "대전",
        "강릉",
        "속초",
        "여수",
        "경주",
        "전주",
        "강남",
        "서울",
        "경기",
    ],
}
