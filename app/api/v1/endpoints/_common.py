"""엔드포인트 공통 유틸리티"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import HTTPException
from core.timezone import date_to_utc
from schemas.common import resolve_period, validate_date_range_d


def resolve_period_or_dates(
    period: str | None,
    start_date: date | None,
    end_date: date | None,
    *,
    error_status: int = 400,
) -> tuple[datetime, datetime]:
    """period 프리셋 또는 start_date+end_date -> UTC datetime 범위."""
    if period:
        return resolve_period(period)
    if bool(start_date) != bool(end_date):
        raise HTTPException(
            status_code=error_status,
            detail="start_date와 end_date를 함께 지정해야 합니다",
        )
    if start_date and end_date:
        validate_date_range_d(start_date, end_date)
        return date_to_utc(start_date), date_to_utc(end_date, end_of_day=True)
    raise HTTPException(
        status_code=error_status,
        detail="period 또는 start_date+end_date를 지정해야 합니다.",
    )


def sanitize_pdf_filename(raw: str) -> str:
    """PDF 저장/ZIP 엔트리용 파일명 정제 — Windows 예약 문자를 밑줄로 치환."""
    import re
    return re.sub(r'[\\/:*?"<>|]', '_', raw)
