from __future__ import annotations

from fastapi import APIRouter, Depends

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
from .endpoints.deps import require_internal_auth

api_router = APIRouter()
_auth = [Depends(require_internal_auth)]

# --- Summaries ---
api_router.include_router(summaries.router, prefix="/summaries", dependencies=_auth)

# --- Tags & Sentiment ---
api_router.include_router(tags.router, prefix="/tags", dependencies=_auth)
api_router.include_router(tags.sentiment_router, prefix="/sentiment", dependencies=_auth)

# --- Analysis ---
api_router.include_router(analysis.router, prefix="/analysis", dependencies=_auth)

# --- Reports ---
api_router.include_router(report.router, prefix="/reports", dependencies=_auth)

# --- Presets ---
api_router.include_router(presets.router, prefix="/presets", dependencies=_auth)

# --- Sync & Processing (이미 라우터 레벨 인증 있음 — 이중 안전) ---
api_router.include_router(sync.router, prefix="/sync")
api_router.include_router(sync.realtime_router, prefix="/realtime")
api_router.include_router(sync.upload_router, prefix="/upload")

# --- Pipeline Console (이미 라우터 레벨 인증 있음) ---
api_router.include_router(pipeline_console.router, prefix="/pipeline")

# --- n8n Webhooks ---
api_router.include_router(n8n.router, prefix="/n8n")

# --- n8n Scheduler (이미 라우터 레벨 인증 있음) ---
api_router.include_router(n8n_scheduler.router, prefix="/n8n/scheduler")
