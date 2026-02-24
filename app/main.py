from __future__ import annotations

import json
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

# 프로젝트 경로 설정
APP_DIR = Path(__file__).parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR.parent))

from core.config import get_settings

settings = get_settings()


# ============================================================
# TZ-Aware JSON Response (안전망)
# ============================================================
class _TZAwareEncoder(json.JSONEncoder):
    """naive datetime에 자동으로 +00:00 offset을 부착하는 인코더."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            if obj.tzinfo is None:
                from core.timezone import UTC
                obj = obj.replace(tzinfo=UTC)
            return obj.isoformat()
        return super().default(obj)


class TZAwareJSONResponse(JSONResponse):
    """모든 API 응답에서 datetime이 항상 offset을 포함하도록 보장."""

    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            cls=_TZAwareEncoder,
            ensure_ascii=False,
        ).encode("utf-8")


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
        print("[Startup] Database engine initialized (asyncpg)")

    print("\n" + "=" * 60)
    print("Review Summary AI - FastAPI 운영팀 모니터링 대시보드")
    print("=" * 60)
    print("\n로컬 접속:    http://localhost:8000")
    print("API 문서:     http://localhost:8000/docs")
    print("\nAPI 엔드포인트:")
    print("  GET  /api/summaries          - 요약 목록")
    print("  GET  /api/tags              - 태그 목록")
    print("  GET  /api/analysis/reviews  - 리뷰 목록 (is_new=true 지원)")
    print("=" * 60 + "\n")

    # 고아 작업 복구 (서버 재시작 시 processing 상태로 방치된 작업 정리)
    await _recover_stale_report_jobs()

    yield

    # 엔진 종료
    if settings.get_database_url():
        await close_db()


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
                print(f"[Startup] 고아 리포트 작업 {recovered}개 복구됨")
    except Exception as e:
        print(f"[Startup] 고아 작업 복구 실패 (무시됨): {e}")


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


# ============================================================
# Global Exception Handlers
# ============================================================
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> TZAwareJSONResponse:
    """HTTPException을 통일된 Envelope 형식으로 변환"""
    return TZAwareJSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.detail, "detail": exc.detail},
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> TZAwareJSONResponse:
    """ValueError를 400 Bad Request로 변환"""
    return TZAwareJSONResponse(
        status_code=400,
        content={"success": False, "error": "Bad Request", "detail": str(exc)},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> TZAwareJSONResponse:
    """처리되지 않은 예외를 500 Internal Server Error로 변환"""
    detail = str(exc) if settings.debug else "Internal server error"
    return TZAwareJSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal Server Error", "detail": detail},
    )


# ============================================================
# Routers
# ============================================================
from api.v1.api import api_router
from api.v1.endpoints.pages import router as pages_router
from api.v1.endpoints.public_summary import router as public_summary_router
from api.v1.endpoints.public_report import router as public_report_router

# API 라우터 (/api/*)
app.include_router(api_router, prefix="/api")

# Public API 라우터 - 외부 연동용 (구체적 경로를 먼저 등록)
app.include_router(public_report_router, prefix="/public/report")  # AI 리포트 외부 제공
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
    import uvicorn
    from core.config import get_settings

    settings = get_settings()
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        reload_dirs=[str(APP_DIR)] if settings.debug else None,
        reload_includes=["*.py", "*.html", "*.js", "*.css"] if settings.debug else None,
    )
