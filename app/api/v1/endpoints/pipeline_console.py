"""파이프라인 콘솔 API 엔드포인트

설정 조회, 전체 재처리 실행, 작업 상태 조회/취소를 제공한다.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from schemas.pipeline_console import FullPipelineRequest, PipelineJobStatusResponse

from .deps import get_pipeline_job_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pipeline-console"])

# --- 설정값 허용 목록 ---
# 절대 노출 금지: openai_api_key, database_password, database_url,
#   database_user, database_host, database_port, database_name,
#   public_api_key, aws_secret_access_key, aws_access_key_id,
#   n8n_api_key, athena_output_bucket, carmore_admin_url

_SAFE_SETTINGS = [
    "llm_provider", "openai_model", "openai_rpm",
    "sentiment_threshold", "lexicon_confident_high", "lexicon_confident_low",
    "batch_size", "n_jobs", "debug",
    "aws_region", "athena_database",
    "sync_hour", "sync_minute",
]


@router.get("/config")
async def get_config() -> dict:
    """분석 파라미터 및 설정값 조회 (읽기 전용)"""
    from core.config import get_settings
    from core.constants import (
        CACHE_MIN_NEW_REVIEWS,
        CACHE_SENTIMENT_DRIFT,
        CACHE_TAG_COUNT_RATIO,
        CONTEXT_WINDOW_SIZE,
        DECAY_LAMBDA,
        EMBEDDING_MODEL,
        HIGH_RATING_THRESHOLD,
        IMPROVEMENT_NEGATIVE_RATIO,
        NEGATIVE_RATING_THRESHOLD,
        REVIEW_CHANGE_THRESHOLD,
        SIMILARITY_THRESHOLD,
        STRENGTH_POSITIVE_RATIO,
    )

    settings = get_settings()

    # settings에서 안전한 필드만 추출
    settings_dict = {}
    for key in _SAFE_SETTINGS:
        val = getattr(settings, key, None)
        if val is not None:
            settings_dict[key] = val

    return {
        "embedding": {
            "model": EMBEDDING_MODEL,
            "similarity_threshold": SIMILARITY_THRESHOLD,
            "context_window_size": CONTEXT_WINDOW_SIZE,
        },
        "rating": {
            "negative_threshold": NEGATIVE_RATING_THRESHOLD,
            "high_threshold": HIGH_RATING_THRESHOLD,
        },
        "report": {
            "strength_positive_ratio": STRENGTH_POSITIVE_RATIO,
            "improvement_negative_ratio": IMPROVEMENT_NEGATIVE_RATIO,
        },
        "cache": {
            "review_change_threshold": REVIEW_CHANGE_THRESHOLD,
            "min_new_reviews": CACHE_MIN_NEW_REVIEWS,
            "tag_count_ratio": CACHE_TAG_COUNT_RATIO,
            "sentiment_drift": CACHE_SENTIMENT_DRIFT,
        },
        "decay": {
            "lambda": DECAY_LAMBDA,
        },
        "pipeline": settings_dict,
    }


@router.post("/run-full", status_code=202)
async def run_full_pipeline(
    body: FullPipelineRequest | None = None,
    svc=Depends(get_pipeline_job_service),
) -> PipelineJobStatusResponse:
    """전체 재처리 파이프라인 비동기 실행"""
    if body is None:
        body = FullPipelineRequest()

    return await svc.submit_job(
        date_from=body.date_from,
        date_to=body.date_to,
        chunk_size=body.chunk_size,
    )


@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    svc=Depends(get_pipeline_job_service),
) -> PipelineJobStatusResponse:
    """파이프라인 작업 상태 조회"""
    result = svc.get_job_status(job_id)
    if result is None:
        raise HTTPException(404, "작업을 찾을 수 없습니다")
    return result


@router.delete("/jobs/{job_id}")
async def cancel_job(
    job_id: str,
    svc=Depends(get_pipeline_job_service),
) -> dict:
    """파이프라인 작업 취소"""
    cancelled = await svc.cancel_job(job_id)
    if not cancelled:
        raise HTTPException(404, "취소할 수 있는 작업이 없습니다")
    return {"success": True, "message": "작업이 취소되었습니다"}
