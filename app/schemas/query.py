"""조회/필터링 관련 스키마 (분석, 요약)"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Query as FQuery
from pydantic import BaseModel, Field


# ── Analysis ─────────────────────────────────────────────────

@dataclass
class ReviewFilterParams:
    """리뷰 필터링 공통 Query 파라미터"""

    regions: list[str] | None = FQuery(None, description="지역 필터 목록")
    companies: list[str] | None = FQuery(None, description="업체명 필터 목록")
    branch_ids: list[int] | None = FQuery(None, description="지점 ID 필터 목록")
    sentiment: str | None = FQuery(
        None,
        pattern="^(positive|negative|neutral)$",
        description="감정 필터 (positive, negative, neutral)",
    )
    date_from: str | None = FQuery(
        None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="시작일 (YYYY-MM-DD)",
    )
    date_to: str | None = FQuery(
        None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="종료일 (YYYY-MM-DD)",
    )
    sort_by: str = FQuery(
        "latest",
        pattern="^(latest|rating_low)$",
        description="정렬 기준 (latest, rating_low)",
    )


# ── Summary ──────────────────────────────────────────────────

class SummaryUpdate(BaseModel):
    """요약 부분 수정 요청 (PATCH)"""

    region: str | None = None
    keywords: list[str] | None = None
    summary_all: str | None = None
    summary_1y: str | None = None
    summary_6m: str | None = None
    summary_3m: str | None = None
    summary_1m: str | None = None


class RegenerateRequest(BaseModel):
    """AI 요약 재생성 요청 (apply-pending/discard-pending용)"""

    period: str = Field("all", pattern="^(all|1y|6m|3m|1m)$")
