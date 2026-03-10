"""
인증 엔드포인트 — 세션 기반 대시보드 인증

- GET  /login  — 로그인 페이지 렌더링
- POST /login  — API 키 검증 후 세션 쿠키 설정
- POST /logout — 세션 무효화

보안:
- 세션 토큰: secrets.token_urlsafe(32) — 256-bit 랜덤
- 쿠키: HttpOnly + SameSite=Strict (XSS로 탈취 불가)
- API 키는 서버에만 존재, 브라우저에 절대 노출되지 않음
"""

from __future__ import annotations

import hmac
import logging
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

_templates_dir = Path(__file__).parent.parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

# ============================================================
# Session Store (in-memory, 단일 프로세스용)
# ============================================================

SESSION_COOKIE_NAME = "review_session"
SESSION_MAX_AGE = 8 * 3600  # 8시간

_sessions: dict[str, float] = {}  # token -> expires_at


def create_session() -> str:
    """새 세션 토큰 생성"""
    _cleanup_expired()
    token = secrets.token_urlsafe(32)
    _sessions[token] = time.time() + SESSION_MAX_AGE
    logger.info("세션 생성 (활성: %d)", len(_sessions))
    return token


def validate_session(token: str | None) -> bool:
    """세션 토큰 유효성 검사"""
    if not token:
        return False
    expires_at = _sessions.get(token)
    if not expires_at:
        return False
    if time.time() > expires_at:
        _sessions.pop(token, None)
        return False
    return True


def invalidate_session(token: str | None) -> None:
    """세션 무효화"""
    if token:
        _sessions.pop(token, None)


def _cleanup_expired() -> None:
    now = time.time()
    expired = [k for k, v in _sessions.items() if now > v]
    for k in expired:
        del _sessions[k]


# ============================================================
# Page Auth Exception — 로그인 리다이렉트 트리거
# ============================================================


class PageAuthRequired(Exception):
    """페이지 접근 시 인증 필요 — main.py exception handler가 로그인으로 리다이렉트"""

    def __init__(self, next_url: str = "/"):
        self.next_url = next_url


# ============================================================
# Endpoints
# ============================================================


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    error: str | None = None,
    next: str = "/",  # noqa: A002
):
    """로그인 페이지 렌더링"""
    settings = get_settings()
    base_path = settings.api_prefix.replace("/api", "")

    # 이미 유효한 세션이 있으면 대시보드로 리다이렉트
    if validate_session(request.cookies.get(SESSION_COOKIE_NAME)):
        return RedirectResponse(url=next or base_path or "/", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "base_path": base_path,
            "error": error,
            "next_url": next,
        },
    )


@router.post("/login")
async def login(
    request: Request,
    api_key: str = Form(...),
    next_url: str = Form(default="/"),
):
    """API 키 검증 후 세션 쿠키 설정"""
    settings = get_settings()
    base_path = settings.api_prefix.replace("/api", "")
    expected = settings.internal_api_key.get_secret_value()
    client_ip = request.client.host if request.client else "unknown"

    if not expected:
        logger.warning("[auth] INTERNAL_API_KEY 미설정 (IP: %s)", client_ip)
        return RedirectResponse(
            url=f"{base_path}/login?error=not_configured",
            status_code=303,
        )

    if not hmac.compare_digest(api_key, expected):
        logger.warning("[auth] 로그인 실패 — 잘못된 키 (IP: %s)", client_ip)
        return RedirectResponse(
            url=f"{base_path}/login?error=invalid&next={next_url}",
            status_code=303,
        )

    token = create_session()
    logger.info("[auth] 로그인 성공 (IP: %s)", client_ip)

    response = RedirectResponse(
        url=next_url or base_path or "/", status_code=303,
    )
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        path="/",
    )
    return response


@router.post("/logout")
async def logout(request: Request):
    """세션 무효화 및 로그인 페이지로 리다이렉트"""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    invalidate_session(token)
    settings = get_settings()
    base_path = settings.api_prefix.replace("/api", "")
    response = RedirectResponse(url=f"{base_path}/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response
