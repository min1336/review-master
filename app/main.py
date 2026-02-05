from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

# 프로젝트 경로 설정
APP_DIR = Path(__file__).parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR.parent))

from core.config import get_settings

settings = get_settings()


# ============================================================
# Lifespan
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan"""
    from infrastructure.scheduler import SyncScheduler
    from infrastructure.scheduler.sync_scheduler import get_scheduler
    from infrastructure.scheduler.monthly_scheduler import get_monthly_scheduler

    print("\n" + "=" * 60)
    print("Review Summary AI - FastAPI 운영팀 모니터링 대시보드")
    print("=" * 60)
    print("\n로컬 접속:    http://localhost:8000")
    print("API 문서:     http://localhost:8000/docs")
    print("\nAPI 엔드포인트:")
    print("  GET  /api/v2/summaries      - 요약 목록")
    print("  GET  /api/tags              - 태그 목록")
    print("  GET  /api/analysis/reviews  - 리뷰 목록 (is_new=true 지원)")
    print("=" * 60 + "\n")

    # 고아 작업 복구 (서버 재시작 시 processing 상태로 방치된 작업 정리)
    await _recover_stale_report_jobs()

    # 스케줄러 시작
    sync_scheduler = get_scheduler()
    await sync_scheduler.start()

    # 월간 AI 스케줄러 시작 (매월 1일)
    monthly_scheduler = get_monthly_scheduler()
    await monthly_scheduler.start()

    yield

    # 스케줄러 종료
    await sync_scheduler.stop()
    await monthly_scheduler.stop()


async def _recover_stale_report_jobs():
    """서버 시작 시 고아 리포트 작업 복구"""
    try:
        from api.v1.endpoints.deps import get_report_job_service
        job_service = get_report_job_service()
        recovered = await job_service.recover_stale_jobs(stale_minutes=30)
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
)


# ============================================================
# Global Exception Handlers
# ============================================================
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """ValueError를 400 Bad Request로 변환"""
    return JSONResponse(
        status_code=400,
        content={"success": False, "error": "Bad Request", "detail": str(exc)},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """처리되지 않은 예외를 500 Internal Server Error로 변환"""
    # 개발 모드에서는 상세 에러 메시지 표시
    detail = str(exc) if settings.debug else "Internal server error"
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal Server Error", "detail": detail},
    )


# ============================================================
# Routers
# ============================================================
from api.v1.api import api_router
from api.v1.endpoints.pages import router as pages_router

# API 라우터 (/api/*)
app.include_router(api_router, prefix="/api")

# 페이지 라우터 (/)
app.include_router(pages_router)

# Static 파일 서빙 (/static/*) - CSS/JS가 HTML에 인라인되어 더 이상 필요 없음
# app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")


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
