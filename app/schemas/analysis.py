"""리뷰 분석 API 스키마"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Query


@dataclass
class ReviewFilterParams:
    """리뷰 필터링 공통 Query 파라미터"""

    regions: list[str] | None = Query(None, description="지역 필터 목록")
    companies: list[str] | None = Query(None, description="업체명 필터 목록")
    branch_ids: list[int] | None = Query(None, description="지점 ID 필터 목록")
    sentiment: str | None = Query(
        None,
        pattern="^(positive|negative|neutral)$",
        description="감정 필터 (positive, negative, neutral)",
    )
    date_from: str | None = Query(
        None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="시작일 (YYYY-MM-DD)",
    )
    date_to: str | None = Query(
        None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="종료일 (YYYY-MM-DD)",
    )
    sort_by: str = Query(
        "latest",
        pattern="^(latest|rating_low)$",
        description="정렬 기준 (latest, rating_low)",
    )
