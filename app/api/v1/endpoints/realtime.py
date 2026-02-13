"""
실시간 리뷰 처리 API 엔드포인트

POST /api/realtime/process - 리뷰 1개 처리
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from schemas.common import api_response
from schemas.realtime import ReviewInput

from .deps import get_realtime_pipeline

router = APIRouter(tags=["realtime"])
logger = logging.getLogger(__name__)


@router.post("/process")
async def api_process_review(
    review: ReviewInput,
    pipeline=Depends(get_realtime_pipeline),
) -> dict[str, Any]:
    """
    리뷰 1개 실시간 처리

    - 내용이 있으면: 형태소 분석 → 태그 매핑 → 감정 분석
    - 내용이 없으면: 별점으로만 감정 판단
    - 결과를 DB에 증분 저장
    """
    try:
        result = await pipeline.process(review.model_dump())

        return api_response({
            "branch_id": result.branch_id,
            "sentiment": result.sentiment,
            "tags": result.tags,
            "saved": result.saved,
            "error": result.error,
        })

    except Exception as e:
        logger.error(f"리뷰 처리 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))
