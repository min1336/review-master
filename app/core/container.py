"""인프라 싱글턴 관리 컨테이너

deps.py와 백그라운드 서비스에서 공통으로 사용하는 인프라 객체의
생명주기를 통합 관리한다.

기존 패턴 통합:
- @lru_cache _get_athena_client() → ServiceContainer.get_athena_client()
- global _realtime_pipeline → ServiceContainer.get_realtime_pipeline()
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


class ServiceContainer:
    """인프라 싱글턴 컨테이너

    @lru_cache, global 변수 등 흩어진 싱글턴 패턴을 하나로 통합.
    """

    _athena_client: object | None = None
    _athena_initialized: bool = False
    _athena_lock: threading.Lock = threading.Lock()
    _realtime_pipeline: object | None = None
    _llm_provider: object | None = None
    _llm_lock: threading.Lock = threading.Lock()

    @classmethod
    def get_athena_client(cls):
        """AthenaClient 싱글턴 반환 (미설정 시 None)"""
        if not cls._athena_initialized:
            with cls._athena_lock:
                if not cls._athena_initialized:
                    try:
                        from core.config import get_settings
                        from infrastructure.athena import AthenaClient

                        settings = get_settings()
                        if settings.aws_access_key_id and settings.athena_output_bucket:
                            cls._athena_client = AthenaClient()
                    except (ImportError, AttributeError, ValueError) as e:
                        logger.warning("Athena 클라이언트 초기화 스킵: %s", e)
                    cls._athena_initialized = True
        return cls._athena_client

    @classmethod
    async def get_realtime_pipeline(cls):
        """RealtimePipeline 싱글턴 반환"""
        if cls._realtime_pipeline is None:
            from domain.pipeline import RealtimePipeline

            cls._realtime_pipeline = RealtimePipeline()
        return cls._realtime_pipeline

    @classmethod
    def get_llm_provider(cls):
        """LLM Provider 싱글턴 반환"""
        if cls._llm_provider is None:
            with cls._llm_lock:
                if cls._llm_provider is None:
                    from core.config import get_settings
                    from infrastructure.llm.openai_provider import OpenAIProvider

                    settings = get_settings()
                    cls._llm_provider = OpenAIProvider(
                        api_key=settings.openai_api_key.get_secret_value(),
                        model=settings.openai_model,
                        rpm=settings.openai_rpm,
                    )
        return cls._llm_provider
