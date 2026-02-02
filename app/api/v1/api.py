from __future__ import annotations

from fastapi import APIRouter

from .endpoints import analysis, report, sentiment, summaries, sync, tags

api_router = APIRouter()

api_router.include_router(summaries.router, prefix="/v2")
api_router.include_router(tags.router, prefix="/tags")
api_router.include_router(sentiment.router, prefix="/sentiment")
api_router.include_router(analysis.router, prefix="/analysis")
api_router.include_router(report.router, prefix="/report")
api_router.include_router(sync.router, prefix="/sync")
