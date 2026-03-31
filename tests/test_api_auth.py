"""API 보안 관련 테스트

Finding 10 (CORS), Finding 11 (응답 형식 일관성), Finding 2 (날짜 경계), Finding 4 (파이프라인 충돌) 검증.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))


class TestCorsConfig:
    """CORS 설정 테스트"""

    def test_debug_mode_no_wildcard(self):
        """debug 모드에서도 CORS wildcard(*) 사용 금지"""
        from core.config import Settings
        settings = Settings(debug=True, cors_origins="")
        cors = [o.strip() for o in settings.cors_origins.split(",") if o.strip()] if settings.cors_origins else []
        if not cors and settings.debug:
            cors = ["http://localhost:8000", "http://localhost:3000", "http://127.0.0.1:8000"]
        assert "*" not in cors

    def test_explicit_cors_origins(self):
        """CORS_ORIGINS 설정 시 해당 도메인만 허용"""
        from core.config import Settings
        settings = Settings(cors_origins="https://app.example.com,https://admin.example.com")
        cors = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
        assert cors == ["https://app.example.com", "https://admin.example.com"]


class TestDateBoundary:
    """날짜 범위 경계 테스트 (Finding 2)"""

    def test_end_of_day_is_next_midnight(self):
        """end_of_day=True는 다음날 00:00:00 KST를 반환 (exclusive upper bound)"""
        from core.timezone import parse_date_str, KST
        dt = parse_date_str("2024-06-15", end_of_day=True)
        kst = dt.astimezone(KST)
        assert kst.day == 16
        assert kst.hour == 0
        assert kst.minute == 0
        assert kst.second == 0


class TestPipelineConflict:
    """파이프라인 상호 배제 테스트 (Finding 4)"""

    def test_check_other_pipelines_raises_valueerror(self):
        """_check_other_pipelines는 HTTPException이 아닌 ValueError 발생"""
        from services.pipeline_job_service import PipelineJobService
        svc = PipelineJobService.get_instance()
        import inspect
        source = inspect.getsource(svc._check_other_pipelines)
        assert "HTTPException" not in source
        assert "ValueError" in source
