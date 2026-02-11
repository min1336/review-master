"""공통 API 응답 헬퍼 + 요청 모델"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel


def api_response(data: Any = None) -> dict[str, Any]:
    """단건 응답 Envelope: {"success": true, "data": ...}"""
    return {"success": True, "data": data}


def api_list_response(
    data: list,
    count: int | None = None,
    total: int | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> dict[str, Any]:
    """목록 응답 Envelope: {"success": true, "data": [...], "count": N, "total": N}"""
    actual_count = count if count is not None else len(data)
    result: dict[str, Any] = {"success": True, "data": data, "count": actual_count}
    if total is not None:
        result["total"] = total
        if limit is not None and offset is not None:
            result["has_next"] = (offset + limit) < total
    return result


def parse_date(date_str: str | None, end_of_day: bool = False) -> datetime | None:
    """
    날짜 문자열을 UTC-aware datetime으로 파싱

    Args:
        date_str: YYYY-MM-DD 형식 문자열 (None이면 None 반환)
        end_of_day: True면 23:59:59로 설정

    Returns:
        UTC-aware datetime 또는 None

    Raises:
        HTTPException(400): 날짜 형식이 잘못된 경우
    """
    if not date_str:
        return None
    try:
        from core.timezone import parse_date_str

        return parse_date_str(date_str, end_of_day=end_of_day)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format: '{date_str}'. Expected YYYY-MM-DD format.",
        ) from e


def validate_date_range(start: datetime | None, end: datetime | None) -> None:
    """시작일/종료일 순서 검증. 시작일이 종료일보다 늦으면 HTTPException(400)"""
    if start and end and start > end:
        raise HTTPException(
            status_code=400,
            detail="시작일이 종료일보다 늦을 수 없습니다.",
        )


class CleanupRequest(BaseModel):
    """리뷰 정리 요청"""

    days: int = 30
    max_per_branch: int = 30
