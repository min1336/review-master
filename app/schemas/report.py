"""리포트 API 요청 스키마"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class ReportRequest(BaseModel):
    """리포트 생성 요청"""

    start_date: date  # YYYY-MM-DD (Pydantic 자동 파싱)
    end_date: date  # YYYY-MM-DD
