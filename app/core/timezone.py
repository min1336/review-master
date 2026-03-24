"""
Timezone 유틸리티 모듈

모든 datetime 처리의 단일 진입점.
내부: UTC 기준 처리 / 외부 표시: KST 변환

Usage:
    from core.timezone import utc_now, to_kst, parse_date_str

    now = utc_now()                          # datetime(2024, 1, 15, 1, 30, tzinfo=UTC)
    kst = to_kst(now)                        # datetime(2024, 1, 15, 10, 30, tzinfo=KST)
    dt = parse_date_str("2024-01-15")        # datetime(2024, 1, 15, 0, 0, tzinfo=UTC)
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

# ── 상수 ──────────────────────────────────────────────────
UTC = timezone.utc
KST = timezone(timedelta(hours=9))


def utc_now() -> datetime:
    """현재 시각을 UTC-aware datetime으로 반환. datetime.now() 대체용."""
    return datetime.now(UTC)


def to_kst(dt: datetime) -> datetime:
    """UTC datetime → KST 변환 (사용자 표시용)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(KST)


def parse_date_str(date_str: str, end_of_day: bool = False) -> datetime:
    """
    YYYY-MM-DD 문자열 → UTC-aware datetime 변환.

    Args:
        date_str: "2024-01-15" 형식
        end_of_day: True이면 23:59:59로 설정

    Returns:
        UTC-aware datetime

    Raises:
        ValueError: 형식이 잘못된 경우
    """
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=KST)
    if end_of_day:
        dt = dt.replace(hour=23, minute=59, second=59)
    return dt.astimezone(UTC)


def date_to_utc(d: date, end_of_day: bool = False) -> datetime:
    """date → UTC-aware datetime 변환. end_of_day=True면 23:59:59."""
    dt = datetime(d.year, d.month, d.day, tzinfo=KST)
    if end_of_day:
        dt = dt.replace(hour=23, minute=59, second=59)
    return dt.astimezone(UTC)


