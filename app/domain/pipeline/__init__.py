"""
파이프라인 모듈 (비동기)

- BasePipeline: 공통 기능 (키워드 추출, 전처리, 감정 분석)
- BatchPipeline: DB 배치 처리 (비동기)
- IncrementalPipeline: API 증분 처리 (비동기)
- KeywordScoreManager: 키워드 점수 관리

Usage:
    # BatchPipeline: DB에서 리뷰 로드하여 처리
    pipeline = BatchPipeline()
    result = await pipeline.run(branch_ids=[1234, 5678])

    # 날짜 범위 필터링
    result = await pipeline.run(
        branch_ids=[1234],
        date_from=datetime(2024, 1, 1),
        date_to=datetime(2024, 12, 31),
        limit=1000
    )

    # IncrementalPipeline: 증분 처리
    inc_pipeline = IncrementalPipeline()
    result = await inc_pipeline.run(branch_ids=[1234, 5678])
"""

from __future__ import annotations

from .pipeline import (
    BasePipeline,
    BatchPipeline,
    IncrementalPipeline,
    KeywordScoreManager,
)

__all__ = [
    "BasePipeline",
    "BatchPipeline",
    "IncrementalPipeline",
    "KeywordScoreManager",
]
