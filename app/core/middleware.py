"""
요청 추적 미들웨어

모든 HTTP 요청에 고유 request_id를 부여하여 로그 역추적을 용이하게 한다.
- 요청/응답 로그에 request_id 포함
- 응답 헤더 X-Request-ID로 클라이언트에 전달
- 정적 파일 요청은 로깅에서 제외 (노이즈 방지)
"""

from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# async-safe request_id — 로깅 필터에서 참조 가능
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

logger = logging.getLogger("app.request")

_SKIP_PREFIXES = ("/static/", "/favicon.ico")

# Content-Security-Policy — XSS 방어 (외부 리소스 로딩 제한)
# unsafe-inline: 대시보드 템플릿의 인라인 스크립트/스타일에 필요
# cdn.jsdelivr.net: Pretendard 폰트, flatpickr 등 CDN 리소스
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "font-src 'self' https://cdn.jsdelivr.net; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


class RequestTracingMiddleware(BaseHTTPMiddleware):
    """요청별 고유 ID 부여, 소요 시간 로깅, 응답 헤더 첨부, 보안 헤더 첨부"""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint,
    ) -> Response:
        req_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request_id_ctx.set(req_id)
        request.state.request_id = req_id

        path = request.url.path
        skip = any(path.startswith(p) for p in _SKIP_PREFIXES)
        t0 = time.monotonic()

        if not skip:
            logger.info("[%s] %s %s", req_id, request.method, path)

        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.exception(
                "[%s] %s %s unhandled exception (%.0fms)",
                req_id, request.method, path, elapsed_ms,
            )
            raise

        elapsed_ms = (time.monotonic() - t0) * 1000
        if not skip:
            logger.info(
                "[%s] %s %s %d (%.0fms)",
                req_id, request.method, path, response.status_code, elapsed_ms,
            )
        response.headers["X-Request-ID"] = req_id
        response.headers["Content-Security-Policy"] = _CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response
