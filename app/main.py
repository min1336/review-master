from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

# 프로젝트 경로 설정
APP_DIR = Path(__file__).parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR.parent))

from core.config import get_settings
from core.response import TZAwareJSONResponse

settings = get_settings()
logger = logging.getLogger(__name__)


# ============================================================
# Lifespan
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan"""
    from repository.database import close_db, init_db

    # SQLAlchemy 엔진 초기화
    db_url = settings.get_database_url()
    if db_url:
        init_db(db_url)
        logger.info("[Startup] Database engine initialized (asyncpg)")

    logger.info("=" * 60)
    logger.info("Review Summary AI - FastAPI 운영팀 모니터링 대시보드")
    logger.info("=" * 60)

    # 고아 작업 복구 (서버 재시작 시 processing 상태로 방치된 작업 정리)
    await _recover_stale_report_jobs()

    # NLP 모델 프리로드 (첫 동기화 시 이벤트 루프 블로킹 방지)
    await _prewarm_nlp_models()

    yield

    # httpx 클라이언트 종료
    await _close_http_clients()

    # 엔진 종료
    if settings.get_database_url():
        await close_db()


async def _prewarm_nlp_models():
    """서버 시작 시 NLP 모델 프리로드 (스레드에서 실행)

    Kiwi (~50MB), HybridClassifier, SentimentAnalyzer를
    서버 시작 시 미리 로드하여 첫 동기화에서 이벤트 루프 블로킹을 방지한다.
    """
    import asyncio

    def _load():
        try:
            from domain.analysis._singletons import (
                get_hybrid_classifier,
                get_kiwi,
                get_sentiment_analyzer,
            )
            get_kiwi()
            get_hybrid_classifier()
            get_sentiment_analyzer()
            logger.info("[Startup] NLP 모델 프리로드 완료 (Kiwi, Classifier, Sentiment)")
        except Exception as e:
            logger.warning("[Startup] NLP 모델 프리로드 실패 (무시됨): %s", e)

    await asyncio.to_thread(_load)


async def _recover_stale_report_jobs():
    """서버 시작 시 고아 리포트 작업 복구"""
    try:
        from repository.database import get_session_factory
        from repository.report_job_repository import ReportJobRepository

        factory = get_session_factory()
        async with factory() as session:
            job_repo = ReportJobRepository(session)
            recovered = await job_repo.mark_stale_jobs_failed(
                stale_minutes=30,
                error_message="서버 재시작으로 인한 작업 중단. 다시 시도해주세요.",
            )
            await session.commit()
            if recovered > 0:
                logger.info("[Startup] 고아 리포트 작업 %d개 복구됨", recovered)
    except Exception as e:
        logger.warning("[Startup] 고아 작업 복구 실패 (무시됨): %s", e)


async def _close_http_clients():
    """모듈 레벨 httpx 클라이언트 정리"""
    try:
        import api.v1.endpoints.n8n as n8n_module
        if n8n_module._http_client is not None:
            await n8n_module._http_client.aclose()
            n8n_module._http_client = None
            logger.info("[Shutdown] httpx client closed")
    except Exception as e:
        logger.warning("[Shutdown] httpx client 종료 실패: %s", e)


# ============================================================
# App
# ============================================================
app = FastAPI(
    title="Review Summary AI",
    description="운영팀 모니터링 대시보드 - Carmore 리뷰 요약 시스템",
    version="2.0.0",
    lifespan=lifespan,
    default_response_class=TZAwareJSONResponse,
)

# CORS 미들웨어
# cors_origins 설정 시 해당 도메인만 허용 + credentials 활성화
# 미설정(빈 문자열) 시: 프로덕션은 same-origin만, 개발은 전체 허용
_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()] if settings.cors_origins else []
if not _cors_origins:
    if settings.debug:
        _cors_origins = ["*"]
        logger.warning("[CORS] debug 모드 — 모든 origin 허용")
    else:
        _cors_origins = []
        logger.info("[CORS] cors_origins 미설정 — same-origin만 허용")
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=_cors_origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

# 요청 추적 미들웨어 — 모든 요청에 X-Request-ID 부여 (로그 역추적용)
# ※ 미들웨어 스택은 역순 실행: 마지막 add_middleware가 가장 먼저 실행됨
from core.middleware import RequestTracingMiddleware

app.add_middleware(RequestTracingMiddleware)


# ============================================================
# Global Exception Handlers
# ============================================================
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> TZAwareJSONResponse:
    """HTTPException을 통일된 Envelope 형식으로 변환"""
    req_id = getattr(request.state, "request_id", "-")
    return TZAwareJSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.detail, "detail": exc.detail, "request_id": req_id},
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> TZAwareJSONResponse:
    """ValueError를 400 Bad Request로 변환"""
    req_id = getattr(request.state, "request_id", "-")
    logger.warning("[%s] ValueError: %s", req_id, exc)
    return TZAwareJSONResponse(
        status_code=400,
        content={"success": False, "error": "Bad Request", "detail": str(exc), "request_id": req_id},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> TZAwareJSONResponse:
    """처리되지 않은 예외를 500 Internal Server Error로 변환 — 상세는 서버 로그에만 기록"""
    req_id = getattr(request.state, "request_id", "-")
    logger.exception("[%s] Unhandled %s", req_id, type(exc).__name__)
    return TZAwareJSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal Server Error", "detail": "Internal server error", "request_id": req_id},
    )


# ============================================================
# Routers
# ============================================================
from api.v1.api import api_router
from api.v1.endpoints.pages import router as pages_router
from api.v1.endpoints.public import summary_router as public_summary_router

# API 라우터 (/api/*)
app.include_router(api_router, prefix="/api")

# Public API 라우터 - 외부 연동용
app.include_router(public_summary_router, prefix="/review")   # 기존 n8n 호환
app.include_router(public_summary_router, prefix="/public")   # 신규 깔끔한 경로

# 페이지 라우터 (/)
app.include_router(pages_router)

# Static 파일 서빙 (/static/*) - 리뷰 상세 테스트 페이지 이미지 등
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")


# Favicon (404 방지)
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    import os
    import socket
    import uvicorn
    from core.config import get_settings

    # Iann : 할당되지 않은 포트 번호를 자동으로 할당해준다.
    def _find_free_port(start: int = 8000, end: int = 8100) -> int:
        for p in range(start, end):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("127.0.0.1", p)) != 0:
                    return p
        return start

    settings = get_settings()
    env_port = int(os.environ.get("PORT", 0))
    port = env_port if 1024 <= env_port <= 65535 else _find_free_port()
    logger.info("[Dev] Starting on port %d", port)
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=settings.debug,
        reload_dirs=[str(APP_DIR)] if settings.debug else None,
        reload_includes=["*.py", "*.html", "*.js", "*.css"] if settings.debug else None,
    )
