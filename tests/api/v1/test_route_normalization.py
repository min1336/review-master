"""
API 라우터 경로 정규화 테스트

검증 대상:
1. 라우트 등록: 새 경로(/summaries, /reports)가 올바르게 등록되었는지
2. 구 경로 제거: /v2 prefix가 완전히 제거되었는지
3. 라우트 순서: 고정 경로가 path parameter 위에 배치되었는지
4. 프론트엔드: HTML 템플릿에서 /v2/ 참조가 모두 치환되었는지
5. poll_url: report.py의 hardcoded poll_url이 새 경로를 사용하는지
6. 엔드포인트 스모크: 주요 경로가 서비스 mock으로 200 응답하는지
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

APP_DIR = Path(__file__).resolve().parent.parent.parent.parent / "app"
TEMPLATES_DIR = APP_DIR / "templates"


def _get_route_paths(app: FastAPI) -> set[str]:
    """앱의 모든 route path 문자열 set."""
    return {route.path for route in app.routes if isinstance(route, APIRoute)}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def app() -> FastAPI:
    """
    api_router를 직접 마운트하는 경량 테스트 앱.

    main.py의 복잡한 의존성(Supabase, 스케줄러, lifespan)을 우회하면서
    실제 라우트 등록 결과만 검증합니다.
    """
    from api.v1.api import api_router

    test_app = FastAPI()
    test_app.include_router(api_router, prefix="/api")
    return test_app


@pytest.fixture(scope="module")
def all_routes(app: FastAPI) -> set[str]:
    return _get_route_paths(app)


# ---------------------------------------------------------------------------
# 1. 라우트 등록 테스트
# ---------------------------------------------------------------------------


class TestRouteRegistration:
    """새 경로가 올바르게 등록되었는지 검증."""

    @pytest.mark.parametrize(
        "path",
        [
            # summaries 리소스
            "/api/summaries",
            "/api/summaries/pending",
            "/api/summaries/stats",
            "/api/summaries/stats/region",
            "/api/summaries/stats/rating",
            "/api/summaries/{branch_id}",
            "/api/summaries/{branch_id}/status",
            "/api/summaries/{branch_id}/regenerate",
            "/api/summaries/{branch_id}/apply-pending",
            "/api/summaries/{branch_id}/discard-pending",
            "/api/summaries/{branch_id}/history",
            "/api/summaries/{branch_id}/approve-pending",
            "/api/summaries/{branch_id}/reject-pending",
            "/api/summaries/{branch_id}/reviews",
            "/api/summaries/{branch_id}/detail",
            "/api/summaries/{branch_id}/car-models",
            # reports 리소스
            "/api/reports/{branch_id}",
            "/api/reports/{branch_id}/list",
            "/api/reports/{branch_id}/review-count",
            "/api/reports/{branch_id}/generate/async",
            "/api/reports/{branch_id}/generate",
            "/api/reports/{branch_id}/regenerate",
            "/api/reports/{branch_id}/job/{job_id}",
            "/api/reports/{branch_id}/pdf",
            "/api/reports/{branch_id}/viewed/{report_id}",
            "/api/reports/{branch_id}/history",
            # 기존 유지 경로
            "/api/tags/list",
            "/api/sentiment/stats",
            "/api/analysis/filters",
        ],
    )
    def test_new_route_exists(self, all_routes: set[str], path: str) -> None:
        assert path in all_routes, f"경로 {path!r}가 등록되지 않았습니다"


class TestOldRoutesRemoved:
    """구 /v2 경로가 완전히 제거되었는지 검증."""

    def test_no_v2_routes(self, all_routes: set[str]) -> None:
        v2_routes = [r for r in all_routes if "/v2" in r]
        assert v2_routes == [], f"/v2 경로가 남아있습니다: {v2_routes}"


# ---------------------------------------------------------------------------
# 2. 라우트 순서 테스트 (summaries router)
# ---------------------------------------------------------------------------


class TestSummariesRouteOrder:
    """
    FastAPI는 라우트를 등록 순서대로 매칭합니다.
    /stats가 /{branch_id}보다 앞에 있어야 'stats' 문자열이
    branch_id로 잘못 매칭되지 않습니다.
    """

    def test_static_routes_before_path_param(self) -> None:
        from api.v1.endpoints.summaries import router

        paths = [route.path for route in router.routes if isinstance(route, APIRoute)]

        static_paths = ["/pending", "/stats", "/stats/region", "/stats/rating"]
        static_indices = []
        for sp in static_paths:
            if sp in paths:
                static_indices.append(paths.index(sp))

        param_indices = [i for i, p in enumerate(paths) if "{branch_id}" in p]

        assert static_indices, "고정 경로를 찾지 못했습니다"
        assert param_indices, "path parameter 경로를 찾지 못했습니다"

        max_static = max(static_indices)
        min_param = min(param_indices)
        assert max_static < min_param, (
            f"고정 경로(max index={max_static})가 "
            f"path parameter 경로(min index={min_param})보다 뒤에 있습니다.\n"
            f"순서: {paths}"
        )


# ---------------------------------------------------------------------------
# 3. Prefix 설정 테스트 (api.py)
# ---------------------------------------------------------------------------


class TestApiRouterPrefixes:
    """api_router에 등록된 prefix가 올바른지 검증."""

    def test_summaries_prefix(self) -> None:
        from api.v1.api import api_router

        paths = [
            route.path for route in api_router.routes if isinstance(route, APIRoute)
        ]
        summaries_paths = [p for p in paths if "summar" in p.lower()]
        assert summaries_paths, "summaries 경로가 api_router에 없습니다"
        for p in summaries_paths:
            assert not p.startswith("/v2"), f"v2 prefix 발견: {p}"
            assert p.startswith("/summaries"), f"잘못된 prefix: {p}"

    def test_reports_prefix(self) -> None:
        from api.v1.api import api_router

        paths = [
            route.path for route in api_router.routes if isinstance(route, APIRoute)
        ]
        report_paths = [p for p in paths if "report" in p.lower()]
        assert report_paths, "report 경로가 api_router에 없습니다"
        for p in report_paths:
            assert not p.startswith("/v2"), f"v2 prefix 발견: {p}"
            assert p.startswith("/reports"), f"잘못된 prefix: {p}"


# ---------------------------------------------------------------------------
# 4. 프론트엔드 경로 테스트
# ---------------------------------------------------------------------------


class TestFrontendPaths:
    """HTML 템플릿에서 구 경로가 완전히 치환되었는지 검증."""

    @pytest.fixture(scope="class")
    def dashboard_html(self) -> str:
        html_path = TEMPLATES_DIR / "dashboard_v2.html"
        return html_path.read_text(encoding="utf-8")

    def test_no_v2_references_in_dashboard(self, dashboard_html: str) -> None:
        matches = re.findall(r"/v2/", dashboard_html)
        assert matches == [], (
            f"dashboard_v2.html에 '/v2/' 참조 {len(matches)}개 남아있습니다"
        )

    def test_summaries_stats_path(self, dashboard_html: str) -> None:
        assert "${API_PREFIX}/summaries/stats" in dashboard_html

    def test_summaries_path(self, dashboard_html: str) -> None:
        assert "${API_PREFIX}/summaries" in dashboard_html

    def test_reports_path(self, dashboard_html: str) -> None:
        assert "${API_PREFIX}/reports/" in dashboard_html

    def test_no_v2_report_references(self, dashboard_html: str) -> None:
        matches = re.findall(r"/v2/report", dashboard_html)
        assert matches == [], "dashboard에 /v2/report 참조가 남아있습니다"

    def test_no_v2_summaries_references(self, dashboard_html: str) -> None:
        matches = re.findall(r"/v2/summaries", dashboard_html)
        assert matches == [], "dashboard에 /v2/summaries 참조가 남아있습니다"

    def test_no_v2_stats_references(self, dashboard_html: str) -> None:
        matches = re.findall(r"/v2/stats", dashboard_html)
        assert matches == [], "dashboard에 /v2/stats 참조가 남아있습니다"


# ---------------------------------------------------------------------------
# 5. poll_url 테스트
# ---------------------------------------------------------------------------


class TestPollUrl:
    """report.py의 hardcoded poll_url이 새 경로를 사용하는지 검증."""

    def test_poll_url_uses_new_path(self) -> None:
        source_path = APP_DIR / "api" / "v1" / "endpoints" / "report.py"
        source = source_path.read_text(encoding="utf-8")

        assert "/api/reports/" in source, "poll_url에 /api/reports/ 경로가 없습니다"
        assert "/api/v2/report/" not in source, (
            "poll_url에 구 경로 /api/v2/report/가 남아있습니다"
        )

    def test_report_docstring_updated(self) -> None:
        source_path = APP_DIR / "api" / "v1" / "endpoints" / "report.py"
        source = source_path.read_text(encoding="utf-8")

        assert "Router: /api/reports" in source


# ---------------------------------------------------------------------------
# 6. summaries.py docstring 테스트
# ---------------------------------------------------------------------------


class TestSummariesDocstring:
    def test_docstring_updated(self) -> None:
        source_path = APP_DIR / "api" / "v1" / "endpoints" / "summaries.py"
        source = source_path.read_text(encoding="utf-8")

        assert "Router: /api/summaries" in source
        assert "Router: /api/v2" not in source


# ---------------------------------------------------------------------------
# 7. main.py startup 메시지 테스트
# ---------------------------------------------------------------------------


class TestMainStartupMessage:
    def test_startup_print_uses_new_path(self) -> None:
        source_path = APP_DIR / "main.py"
        source = source_path.read_text(encoding="utf-8")

        assert "/api/summaries" in source
        assert "/api/v2/summaries" not in source


# ---------------------------------------------------------------------------
# 8. 엔드포인트 스모크 테스트 (mocked services)
# ---------------------------------------------------------------------------


def _mock_summary_service() -> AsyncMock:
    """SummaryService mock."""
    svc = AsyncMock()
    svc.get_summaries.return_value = []
    svc.get_pending_summaries.return_value = []

    stats_mock = MagicMock()
    stats_mock.to_dict.return_value = {"total": 0}
    svc.get_stats.return_value = stats_mock

    region_mock = MagicMock()
    region_mock.to_dict.return_value = {"region": "서울", "count": 0}
    svc.get_region_stats.return_value = [region_mock]

    rating_mock = MagicMock()
    rating_mock.to_dict.return_value = {"distribution": {}}
    svc.get_rating_stats.return_value = rating_mock

    svc.get_summary.return_value = {"branch_id": 1, "summary": "test"}
    return svc


def _mock_report_service() -> AsyncMock:
    """ReportService mock."""
    svc = AsyncMock()
    svc.get_report_list.return_value = []
    return svc


@pytest.fixture
def mock_app(app: FastAPI) -> FastAPI:
    """DI를 mock으로 오버라이드한 테스트용 앱."""
    from api.v1.endpoints.deps import get_report_service, get_summary_service

    mock_svc = _mock_summary_service()
    mock_report_svc = _mock_report_service()

    app.dependency_overrides[get_summary_service] = lambda: mock_svc
    app.dependency_overrides[get_report_service] = lambda: mock_report_svc

    yield app

    app.dependency_overrides.clear()


@pytest.mark.asyncio
class TestEndpointSmoke:
    """주요 엔드포인트가 올바른 경로에서 응답하는지 스모크 테스트."""

    async def test_get_summaries(self, mock_app: FastAPI) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=mock_app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/summaries")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True

    async def test_get_pending_summaries(self, mock_app: FastAPI) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=mock_app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/summaries/pending")
            assert resp.status_code == 200

    async def test_get_stats(self, mock_app: FastAPI) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=mock_app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/summaries/stats")
            assert resp.status_code == 200

    async def test_get_region_stats(self, mock_app: FastAPI) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=mock_app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/summaries/stats/region")
            assert resp.status_code == 200

    async def test_get_rating_stats(self, mock_app: FastAPI) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=mock_app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/summaries/stats/rating")
            assert resp.status_code == 200

    async def test_get_summary_detail(self, mock_app: FastAPI) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=mock_app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/summaries/1")
            assert resp.status_code == 200

    async def test_get_report_list(self, mock_app: FastAPI) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=mock_app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/reports/1/list")
            assert resp.status_code == 200

    async def test_old_v2_summaries_returns_not_found(self, mock_app: FastAPI) -> None:
        """구 /v2/summaries 경로는 404여야 합니다."""
        async with AsyncClient(
            transport=ASGITransport(app=mock_app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v2/summaries")
            assert resp.status_code in (404, 405)

    async def test_old_v2_report_returns_not_found(self, mock_app: FastAPI) -> None:
        """구 /v2/report/{id}/list 경로는 404여야 합니다."""
        async with AsyncClient(
            transport=ASGITransport(app=mock_app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v2/report/1/list")
            assert resp.status_code in (404, 405)

    async def test_stats_not_captured_as_branch_id(self, mock_app: FastAPI) -> None:
        """
        /stats가 /{branch_id}로 잘못 매칭되지 않는지 검증.
        stats 경로는 200을 반환하고, 올바른 stats 데이터를 포함해야 합니다.
        """
        async with AsyncClient(
            transport=ASGITransport(app=mock_app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/summaries/stats")
            assert resp.status_code == 200
            data = resp.json()
            # stats 응답에는 'total' 키가 있어야 하고,
            # branch_id로 매칭된 경우 summary 데이터 형태가 됨
            assert "total" in data.get("data", {})
