from __future__ import annotations

from fastapi import APIRouter

from .endpoints import (
    analysis,
    monthly_scheduler,
    realtime,
    report,
    sentiment,
    summaries,
    sync,
    tags,
)

api_router = APIRouter()

# --- Core Resources ---
api_router.include_router(summaries.router, prefix="/summaries")
api_router.include_router(tags.router, prefix="/tags")
api_router.include_router(sentiment.router, prefix="/sentiment")
api_router.include_router(analysis.router, prefix="/analysis")
api_router.include_router(report.router, prefix="/reports")

# --- Sync & Processing ---
api_router.include_router(sync.router, prefix="/sync")
api_router.include_router(realtime.router, prefix="/realtime")

# --- Scheduler ---
api_router.include_router(monthly_scheduler.router, prefix="/scheduler/monthly")
