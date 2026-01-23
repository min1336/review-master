"""
FastAPI 의존성 주입 컨테이너

모든 Repository와 Service의 의존성을 관리합니다.

Usage:
    from api.deps import get_summary_service

    @router.get("/summaries")
    async def api_summaries(
        service: SummaryService = Depends(get_summary_service)
    ):
        return await service.get_summaries()
"""

from fastapi import Depends
from supabase import AsyncClient

from crud.session import get_client
from crud import UnitOfWork


# ============================================================
# Database Client
# ============================================================


async def get_db_client() -> AsyncClient:
    """Supabase AsyncClient 의존성"""
    return await get_client()


# ============================================================
# UnitOfWork (권장)
# ============================================================


async def get_uow(client: AsyncClient = Depends(get_db_client)) -> UnitOfWork:
    """UnitOfWork 의존성 - 여러 Repository 묶음"""
    return UnitOfWork(client)


# ============================================================
# Services
# 순환 참조 방지를 위해 함수 내부에서 import
# ============================================================


async def get_summary_service(uow: UnitOfWork = Depends(get_uow)):
    """SummaryService 의존성"""
    from services.summary_service import SummaryService
    return SummaryService(uow)


async def get_tag_service(uow: UnitOfWork = Depends(get_uow)):
    """TagService 의존성"""
    from services.tag_service import TagService
    return TagService(uow)


async def get_sentiment_service(uow: UnitOfWork = Depends(get_uow)):
    """SentimentService 의존성"""
    from services.sentiment_service import SentimentService
    return SentimentService(uow)


async def get_carmore_service(uow: UnitOfWork = Depends(get_uow)):
    """CarmoreService 의존성"""
    from services.carmore_service import CarmoreService
    return CarmoreService(uow)
