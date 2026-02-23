"""n8n 웹훅 프록시 엔드포인트

프론트엔드 CORS 제약을 우회하여 n8n 웹훅을 호출한다.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from schemas.common import api_response

logger = logging.getLogger(__name__)
router = APIRouter(tags=["n8n"])

N8N_BASE = "https://n8n-cloud.carmore.kr"
N8N_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=5.0)


async def _call_n8n(path: str) -> dict[str, Any]:
    """n8n 웹훅을 호출하고 응답을 반환한다."""
    url = f"{N8N_BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=N8N_TIMEOUT) as client:
            resp = await client.post(url)
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException:
        logger.error("n8n webhook timeout: %s", url)
        raise HTTPException(status_code=504, detail="n8n 웹훅 응답 시간 초과")
    except httpx.HTTPStatusError as e:
        logger.error("n8n webhook error %s: %s", e.response.status_code, url)
        raise HTTPException(
            status_code=502,
            detail=f"n8n 웹훅 오류 ({e.response.status_code})",
        )
    except httpx.HTTPError as e:
        logger.error("n8n webhook connection error: %s", e)
        raise HTTPException(status_code=502, detail="n8n 웹훅 연결 실패")


@router.post("/review-sync")
async def n8n_review_sync() -> dict[str, Any]:
    """신규 리뷰 동기화 (n8n 웹훅)"""
    result = await _call_n8n("/webhook-test/review-sync")
    return api_response(result)


@router.post("/generate-summary")
async def n8n_generate_summary() -> dict[str, Any]:
    """월별 요약/리포트 생성 (n8n 웹훅)"""
    result = await _call_n8n("/webhook-test/generate-summary")
    return api_response(result)
