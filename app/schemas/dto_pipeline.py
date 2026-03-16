"""Pipeline 관련 DTO"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from core.timezone import utc_now


class PipelineConfigDTO(BaseModel):
    """파이프라인 설정 DTO"""

    # 필터링 설정
    min_review_length: int = 5

    # 감정분석 설정
    sentiment_threshold: float = 0.45
    confident_high: float = 0.7
    confident_low: float = 0.3
    use_bert: bool = True

    # 키워드 설정
    top_n_keywords: int = 10
    use_keyword_weights: bool = True

    # 병렬 처리 설정
    use_parallel: bool = True
    n_jobs: int = -1

    # LLM 설정
    llm_provider: str = "openai"
    max_tokens: int = 300
    temperature: float = 0.7


class PipelineStepResultDTO(BaseModel):
    """파이프라인 단일 스텝 결과 DTO"""

    step_name: str
    success: bool
    input_count: int
    output_count: int
    duration_seconds: float = 0.0
    error_message: str | None = None


class PipelineResultDTO(BaseModel):
    """파이프라인 전체 실행 결과 DTO"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool
    total_reviews: int
    processed_reviews: int
    total_branches: int
    summaries_generated: int
    steps: list[PipelineStepResultDTO] = Field(default_factory=list)
    total_duration_seconds: float = 0.0
    error_message: str | None = None
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None

    def add_step(self, step: PipelineStepResultDTO):
        """스텝 결과 추가"""
        self.steps.append(step)

    @property
    def failed_steps(self) -> list[str]:
        """실패한 스텝 이름 목록"""
        return [s.step_name for s in self.steps if not s.success]

    @model_serializer
    def _serialize(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "total_reviews": self.total_reviews,
            "processed_reviews": self.processed_reviews,
            "total_branches": self.total_branches,
            "summaries_generated": self.summaries_generated,
            "steps": [s.model_dump() for s in self.steps],
            "total_duration_seconds": self.total_duration_seconds,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }
