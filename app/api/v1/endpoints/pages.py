"""
페이지 라우터 - HTML 템플릿 렌더링

역할:
- 대시보드 메인 페이지 (/)
- 태그 테스터 페이지 (/tag-tester)
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from core.config import get_settings

router = APIRouter(tags=["pages"])
settings = get_settings()

# 템플릿 디렉토리 설정
_templates_dir = Path(__file__).parent.parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


def _page_context() -> dict:
    """모든 페이지 라우트에 공통으로 전달되는 context"""
    return {
        "api_prefix": settings.api_prefix,
        "base_path": settings.api_prefix.replace("/api", ""),
    }


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """메인 대시보드"""
    return templates.TemplateResponse(
        request=request,
        name="dashboard_v2.html",
        context=_page_context(),
    )


@router.get("/tag-tester", response_class=HTMLResponse)
async def tag_tester(request: Request):
    """태그 분석 테스트 페이지"""
    return templates.TemplateResponse(
        request=request,
        name="tag_tester.html",
        context=_page_context(),
    )


@router.get("/review-detail-test", response_class=HTMLResponse)
async def review_detail_test(request: Request):
    """리뷰 요약 테스트 페이지"""
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
