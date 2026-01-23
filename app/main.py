"""
Review Summary AI - FastAPI 운영팀 모니터링 대시보드
"""
import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI

# 프로젝트 경로 설정
APP_DIR = Path(__file__).parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR.parent))


# ============================================================
# Lifespan
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan"""
    # Startup
    print("\n" + "=" * 60)
    print("Review Summary AI - FastAPI 운영팀 모니터링 대시보드")
    print("=" * 60)
    print("\n접속: http://localhost:8000")
    print("API 문서: http://localhost:8000/docs")
    print("\nAPI 엔드포인트:")
    print("  GET  /api/v2/summaries      - 요약 목록")
    print("  GET  /api/tags              - 태그 목록")
    print("=" * 60 + "\n")

    yield


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
# Routers
# ============================================================
# Routers
# ============================================================
from api.v1.api import api_router
from api.v1.endpoints.pages import router as pages_router

# API 라우터 (/api/*)
app.include_router(api_router, prefix="/api")

# 페이지 라우터 (/)
app.include_router(pages_router)


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
    )
