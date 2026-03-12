"""n8n 웹훅 프록시 엔드포인트

프론트엔드 CORS 제약을 우회하여 n8n 웹훅을 호출한다.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from schemas.common import ApiResponseModel, api_response

from .deps import require_internal_auth

logger = logging.getLogger(__name__)
router = APIRouter(tags=["n8n"])

N8N_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=5.0)

# Module-level reusable client (avoids creating a new connection per request)
_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=N8N_TIMEOUT)
    return _http_client


def _webhook_prefix() -> str:
    """로컬(n8n_test_mode=True)이면 /webhook-test, Docker/실서버는 /webhook"""
    from core.config import get_settings
    return "/webhook-test" if get_settings().n8n_test_mode else "/webhook"


async def _call_n8n(path: str) -> dict[str, Any]:
    """n8n 웹훅을 호출하고 응답을 반환한다."""
    from core.config import get_settings
    url = f"{get_settings().n8n_base_url}{_webhook_prefix()}{path}"
    client = _get_client()
    try:
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


@router.post("/webhook/jotform-cancellation", dependencies=[Depends(require_internal_auth)])
async def jotform_cancellation_proxy(request: Request) -> dict[str, Any]:
    """Jotform webhook → slack-bot 프록시. n8n 외부 경로 제약 우회용."""
    body = await request.body()
    if len(body) > 1_000_000:
        raise HTTPException(status_code=413, detail="페이로드가 너무 큽니다 (1MB 제한)")
    content_type = request.headers.get("content-type", "")
    if content_type and "form" not in content_type and "json" not in content_type:
        raise HTTPException(status_code=400, detail="지원하지 않는 Content-Type")
    from core.config import get_settings
    client = _get_client()
    try:
        resp = await client.post(
            f"{get_settings().slack_bot_base_url}/webhook/cancellation",
            content=body,
            headers={"Content-Type": content_type},
        )
        return resp.json()
    except httpx.HTTPError as e:
        logger.error("slack-bot webhook proxy error: %s", e)
        raise HTTPException(status_code=502, detail="slack-bot 웹훅 연결 실패")


@router.post("/review-sync", response_model=ApiResponseModel[dict], dependencies=[Depends(require_internal_auth)])
async def n8n_review_sync() -> dict[str, Any]:
    """신규 리뷰 동기화 (n8n 웹훅)"""
    result = await _call_n8n("/review-sync")
    return api_response(result)


@router.post("/generate-summary", response_model=ApiResponseModel[dict], dependencies=[Depends(require_internal_auth)])
async def n8n_generate_summary() -> dict[str, Any]:
    """월별 요약/리포트 생성 (n8n 웹훅)"""
    result = await _call_n8n("/generate-summary")
    return api_response(result)
