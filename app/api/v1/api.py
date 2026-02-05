from __future__ import annotations

from fastapi import APIRouter

from .endpoints import analysis, monthly_scheduler, realtime, report, scheduler_settings, sentiment, summaries, sync, tags

api_router = APIRouter()

api_router.include_router(summaries.router, prefix="/v2")
api_router.include_router(tags.router, prefix="/tags")
api_router.include_router(sentiment.router, prefix="/sentiment")
api_router.include_router(analysis.router, prefix="/analysis")
api_router.include_router(report.router, prefix="/v2/report")  # /v2 아래로 이동
api_router.include_router(sync.router, prefix="/sync")
api_router.include_router(realtime.router, prefix="/realtime")
api_router.include_router(scheduler_settings.router, prefix="/scheduler/settings")
api_router.include_router(monthly_scheduler.router, prefix="/scheduler/monthly")
