"""
페이지 라우터 - HTML 템플릿 렌더링

역할:
- 대시보드 메인 페이지 (/)
"""

from __future__ import annotations

from pathlib import Path

from core.config import get_settings
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["pages"])
settings = get_settings()

# 템플릿 디렉토리 설정
_templates_dir = Path(__file__).parent.parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

# shared-utils.js를 모듈 로드 시 읽어서 인라인 삽입 (리버스 프록시 503 우회)
_static_dir = Path(__file__).parent.parent.parent.parent / "static"
_shared_utils_js = (_static_dir / "js" / "shared-utils.js").read_text(encoding="utf-8")


def _page_context() -> dict:
    """모든 페이지 라우트에 공통으로 전달되는 context"""
    return {
        "api_prefix": settings.api_prefix,
        "base_path": settings.api_prefix.replace("/api", ""),
        "carmore_admin_url": settings.carmore_admin_url,
        "shared_utils_js": _shared_utils_js,
        "internal_api_key": settings.internal_api_key.get_secret_value(),
    }


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """메인 대시보드"""
    return templates.TemplateResponse(
        request=request,
        name="dashboard_v2.html",
        context=_page_context(),
    )


if settings.debug:
    @router.get("/review-detail-test", response_class=HTMLResponse)
    async def review_detail_test(request: Request):
        """리뷰 요약 테스트 페이지 (debug 모드에서만 노출)"""
        return templates.TemplateResponse(
            request=request,
            name="review_detail_test.html",
            context=_page_context(),
        )


@router.get("/analysis", response_class=HTMLResponse)
async def analysis(request: Request):
    """리뷰 분석 페이지"""
    return templates.TemplateResponse(
        request=request,
        name="analysis.html",
        context=_page_context(),
    )


@router.get("/scheduler", response_class=HTMLResponse)
async def scheduler(request: Request):
    """n8n 스케줄러 관리 페이지"""
    return templates.TemplateResponse(
        request=request,
        name="scheduler.html",
        context=_page_context(),
    )


@router.get("/pipeline-console", response_class=HTMLResponse)
async def pipeline_console(request: Request):
    """파이프라인 콘솔 페이지"""
    return templates.TemplateResponse(
        request=request,
        name="pipeline_console.html",
        context=_page_context(),
    )
