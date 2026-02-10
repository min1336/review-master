"""공통 API 응답 헬퍼 + 요청 모델"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def api_response(data: Any = None) -> dict[str, Any]:
    """단건 응답 Envelope: {"success": true, "data": ...}"""
    return {"success": True, "data": data}


def api_list_response(data: list, count: int | None = None) -> dict[str, Any]:
    """목록 응답 Envelope: {"success": true, "data": [...], "count": N}"""
    return {"success": True, "data": data, "count": count if count is not None else len(data)}


class CleanupRequest(BaseModel):
    """리뷰 정리 요청"""

    days: int = 30
    max_per_branch: int = 30
