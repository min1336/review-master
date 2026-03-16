from __future__ import annotations

from fastapi import APIRouter

from .endpoints import (
    analysis,
    n8n,
    n8n_scheduler,
    pipeline_console,
    presets,
    report,
    summaries,
    sync,
    tags,
)

api_router = APIRouter()

# --- Summaries ---
api_router.include_router(summaries.router, prefix="/summaries")

# --- Tags & Sentiment ---
api_router.include_router(tags.router, prefix="/tags")
api_router.include_router(tags.sentiment_router, prefix="/sentiment")

# --- Analysis ---
api_router.include_router(analysis.router, prefix="/analysis")

# --- Reports ---
api_router.include_router(report.router, prefix="/reports")

# --- Presets ---
api_router.include_router(presets.router, prefix="/presets")

# --- Sync & Processing ---
api_router.include_router(sync.router, prefix="/sync")
api_router.include_router(sync.realtime_router, prefix="/realtime")
api_router.include_router(sync.upload_router, prefix="/upload")

# --- Pipeline Console ---
api_router.include_router(pipeline_console.router, prefix="/pipeline")

# --- n8n Webhooks ---
api_router.include_router(n8n.router, prefix="/n8n")

# --- n8n Scheduler ---
api_router.include_router(n8n_scheduler.router, prefix="/n8n/scheduler")
