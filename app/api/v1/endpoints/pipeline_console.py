"""파이프라인 콘솔 API 엔드포인트

설정 조회, 전체 재처리 실행, 작업 상태 조회/취소를 제공한다.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from schemas.pipeline_console import FullPipelineRequest, PipelineJobStatusResponse

from .deps import get_pipeline_job_service, get_sync_job_service, get_upload_job_service, require_internal_auth

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pipeline-console"], dependencies=[Depends(require_internal_auth)])

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


@router.get("/active-jobs")
async def get_active_jobs(
    sync_svc=Depends(get_sync_job_service),
    pipeline_svc=Depends(get_pipeline_job_service),
    upload_svc=Depends(get_upload_job_service),
) -> dict:
    """활성 작업 조회 (페이지 재진입 시 진행률 복원용)"""
    result: dict = {}

    sync_active = sync_svc.get_active_job()
    if sync_active is not None:
        result["sync"] = sync_active.model_dump(mode="json")

    pipeline_active = pipeline_svc.get_active_job()
    if pipeline_active is not None:
        result["pipeline"] = pipeline_active.model_dump(mode="json")

    upload_active = upload_svc.get_active_job()
    if upload_active is not None:
        result["upload"] = upload_active.model_dump(mode="json")

    return result


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


# --- 수정 가능한 설정 매핑 ---
# (group, key) -> (source, attr_name, type)
# source: "constants" -> core.constants 모듈 변수, "settings" -> Settings 인스턴스 속성
_EDITABLE_MAP: dict[tuple[str, str], tuple[str, str, type]] = {
    # embedding
    ("embedding", "similarity_threshold"): ("constants", "SIMILARITY_THRESHOLD", float),
    ("embedding", "context_window_size"): ("constants", "CONTEXT_WINDOW_SIZE", int),
    # rating
    ("rating", "negative_threshold"): ("constants", "NEGATIVE_RATING_THRESHOLD", float),
    ("rating", "high_threshold"): ("constants", "HIGH_RATING_THRESHOLD", float),
    # report
    ("report", "strength_positive_ratio"): ("constants", "STRENGTH_POSITIVE_RATIO", int),
    ("report", "improvement_negative_ratio"): ("constants", "IMPROVEMENT_NEGATIVE_RATIO", int),
    # cache
    ("cache", "review_change_threshold"): ("constants", "REVIEW_CHANGE_THRESHOLD", int),
    ("cache", "min_new_reviews"): ("constants", "CACHE_MIN_NEW_REVIEWS", int),
    ("cache", "tag_count_ratio"): ("constants", "CACHE_TAG_COUNT_RATIO", float),
    ("cache", "sentiment_drift"): ("constants", "CACHE_SENTIMENT_DRIFT", float),
    # decay
    ("decay", "lambda"): ("constants", "DECAY_LAMBDA", float),
    # pipeline (settings)
    ("pipeline", "openai_rpm"): ("settings", "openai_rpm", int),
    ("pipeline", "sentiment_threshold"): ("settings", "sentiment_threshold", float),
    ("pipeline", "batch_size"): ("settings", "batch_size", int),
    ("pipeline", "n_jobs"): ("settings", "n_jobs", int),
    ("pipeline", "sync_hour"): ("settings", "sync_hour", int),
    ("pipeline", "sync_minute"): ("settings", "sync_minute", int),
}


class ConfigUpdateRequest(BaseModel):
    """설정 변경 요청 — 그룹별 key-value 형태

    예시: {"pipeline": {"openai_rpm": 3000}, "embedding": {"similarity_threshold": 0.4}}
    """

    model_config = {"extra": "allow"}


_config_lock = asyncio.Lock()


@router.put("/config")
async def update_config(body: ConfigUpdateRequest) -> dict:
    """설정값 런타임 수정 (서버 재시작 시 원래 값 복원)

    body 형식: { "group": { "key": value, ... }, ... }
    NOTE: 단일 프로세스 환경 전용. 다중 워커 시 워커 간 동기화 불가.
    """
    import core.constants as constants_module
    from core.config import get_settings

    settings = get_settings()
    updated: dict[str, dict[str, object]] = {}
    errors: list[str] = []

    async with _config_lock:
        for group, fields in body.model_dump().items():
            if not isinstance(fields, dict):
                continue
            for key, value in fields.items():
                mapping = _EDITABLE_MAP.get((group, key))
                if mapping is None:
                    errors.append(f"{group}.{key}: 수정 불가능한 설정")
                    continue

                source, attr_name, expected_type = mapping
                try:
                    cast_value = expected_type(value)
                except (ValueError, TypeError):
                    errors.append(f"{group}.{key}: {expected_type.__name__} 타입이어야 합니다")
                    continue

                if source == "constants":
                    setattr(constants_module, attr_name, cast_value)
                else:
                    setattr(settings, attr_name, cast_value)

                updated.setdefault(group, {})[key] = cast_value

    result: dict[str, object] = {"updated": updated}
    if errors:
        result["errors"] = errors

    logger.info("설정 런타임 수정: %s", updated)
    return result


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
