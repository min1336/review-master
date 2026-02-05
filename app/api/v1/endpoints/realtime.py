"""
실시간 리뷰 처리 API 엔드포인트

POST /api/realtime/process - 리뷰 1개 처리
GET /api/realtime/test - 테스트용 (고정 데이터)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()
logger = logging.getLogger(__name__)


class ReviewInput(BaseModel):
    """리뷰 입력 스키마"""

    branch_id: int = Field(..., description="업체 ID")
    content: str = Field(default="", description="리뷰 내용")
    rating_service: float | None = Field(default=None, description="서비스 평점 (1-5)")
    rating_car: float | None = Field(default=None, description="차량 평점 (1-5)")
    rating_convenience: float | None = Field(default=None, description="편의성 평점 (1-5)")


class ProcessResult(BaseModel):
    """처리 결과 스키마"""

    branch_id: int
    sentiment: str
    tags: list[dict]
    saved: bool
    error: str | None = None


@router.post("/process", response_model=ProcessResult)
async def process_review(review: ReviewInput):
    """
    리뷰 1개 실시간 처리

    - 내용이 있으면: 형태소 분석 → 태그 매핑 → 감정 분석
    - 내용이 없으면: 별점으로만 감정 판단
    - 결과를 DB에 증분 저장
    """
    try:
        from domain.pipeline import RealtimePipeline

        pipeline = RealtimePipeline()
        result = await pipeline.process(review.model_dump())

        return ProcessResult(
            branch_id=result.branch_id,
            sentiment=result.sentiment,
            tags=result.tags,
            saved=result.saved,
            error=result.error,
        )

    except Exception as e:
        logger.error(f"리뷰 처리 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))