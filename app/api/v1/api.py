from __future__ import annotations

from fastapi import APIRouter

from .endpoints import (
    analysis,
    n8n,
    n8n_scheduler,
    presets,
    realtime,
    report,
    report_generate,
    sentiment,
    summaries,
    summary_branch,
    sync,
    tags,
    upload,
)

api_router = APIRouter()

# --- Summaries ---
api_router.include_router(summaries.router, prefix="/summaries")
api_router.include_router(summary_branch.router, prefix="/summaries")

# --- Tags & Sentiment ---
api_router.include_router(tags.router, prefix="/tags")
api_router.include_router(sentiment.router, prefix="/sentiment")

# --- Analysis ---
api_router.include_router(analysis.router, prefix="/analysis")

# --- Reports ---
api_router.include_router(report.router, prefix="/reports")
api_router.include_router(report_generate.router, prefix="/reports")

# --- Presets ---
api_router.include_router(presets.router, prefix="/presets")

# --- Sync & Processing ---
api_router.include_router(sync.router, prefix="/sync")
api_router.include_router(realtime.router, prefix="/realtime")
api_router.include_router(upload.router, prefix="/upload")

# --- n8n Webhooks ---
api_router.include_router(n8n.router, prefix="/n8n")

# --- n8n Scheduler ---
api_router.include_router(n8n_scheduler.router, prefix="/n8n/scheduler")
