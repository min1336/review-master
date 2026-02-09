"""pytest 공통 fixtures"""

import sys
from pathlib import Path

# app 디렉토리를 sys.path에 추가 (상대 경로)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from schemas.dto import ReviewDTO, ProcessedReviewDTO


# ==============================================================================
# Athena 리뷰 원본 dict fixtures
# ==============================================================================


@pytest.fixture
def sample_athena_reviews():
    """Athena에서 가져온 리뷰 dict 리스트 샘플"""
    return [
        {
            "review_id": "1001",
            "branch_id": "100",
            "content": "직원분들이 정말 친절하고 차량도 깨끗했습니다. 다음에도 이용할게요!",
            "branch_name": "제주공항점",
            "rating_service": "5.0",
            "rating_car": "5.0",
            "rating_convenience": "4.5",
            "review_date": "2026-02-01 10:00:00",
            "helpful_count": "5",
            "car_type": "아반떼",
            "company_name": "카모아렌트카",
            "status": "1",
        },
        {
            "review_id": "1002",
            "branch_id": "100",
            "content": "차량 상태가 좋지 않았고 냄새도 났습니다. 청결 상태 개선 필요합니다.",
            "branch_name": "제주공항점",
            "rating_service": "3.0",
            "rating_car": "2.5",
            "rating_convenience": "3.0",
            "review_date": "2026-02-02 11:00:00",
            "helpful_count": "2",
            "car_type": "소나타",
            "company_name": "카모아렌트카",
            "status": "1",
        },
        {
            "review_id": "1003",
            "branch_id": "200",
            "content": "가격이 저렴하고 픽업도 빨랐어요. 만족합니다.",
            "branch_name": "김포공항점",
            "rating_service": "4.5",
            "rating_car": "4.0",
            "rating_convenience": "5.0",
            "review_date": "2026-02-03 12:00:00",
            "helpful_count": "3",
            "car_type": "K5",
            "company_name": "SK렌트카",
            "status": "1",
        },
    ]


# ==============================================================================
# ReviewDTO fixtures
# ==============================================================================


@pytest.fixture
def sample_review_dto():
    """ReviewDTO 샘플"""
    return ReviewDTO(
        id=1001,
        branch_id=100,
        content="직원분들이 정말 친절하고 차량도 깨끗했습니다.",
        branch_name="제주공항점",
        rating=5.0,
        created_at=datetime(2026, 2, 1, 10, 0, 0),
        like_count=5,
        is_blind=False,
        car_model="아반떼",
        company_name="카모아렌트카",
        status="1",
    )


# ==============================================================================
# ProcessedReviewDTO fixtures
# ==============================================================================


@pytest.fixture
def sample_processed_reviews():
    """ProcessedReviewDTO 리스트 샘플 (지점 100 - 2개 리뷰)"""
    return [
        ProcessedReviewDTO(
            review=ReviewDTO(
                id=1001,
                branch_id=100,
                content="직원분들이 정말 친절하고 차량도 깨끗했습니다.",
                branch_name="제주공항점",
                rating=5.0,
                created_at=datetime(2026, 2, 1, 10, 0, 0),
                car_model="아반떼",
                company_name="카모아렌트카",
            ),
            keywords=["친절", "깨끗"],
            sentiment="positive",
            sentiment_score=0.85,
            tag_sentiments={
                "친절도": {"positive": ["친절"], "negative": [], "neutral": []},
                "청결": {"positive": ["깨끗"], "negative": [], "neutral": []},
            },
        ),
        ProcessedReviewDTO(
            review=ReviewDTO(
                id=1002,
                branch_id=100,
                content="차량 상태가 좋지 않았고 냄새도 났습니다.",
                branch_name="제주공항점",
                rating=2.5,
                created_at=datetime(2026, 2, 2, 11, 0, 0),
                car_model="소나타",
                company_name="카모아렌트카",
            ),
            keywords=["냄새", "상태"],
            sentiment="negative",
            sentiment_score=0.25,
            tag_sentiments={
                "청결": {"positive": [], "negative": ["냄새"], "neutral": []},
                "차량상태": {"positive": [], "negative": ["상태"], "neutral": []},
            },
        ),
    ]


@pytest.fixture
def sample_multi_branch_reviews():
    """여러 지점에 걸친 ProcessedReviewDTO 리스트"""
    return [
        ProcessedReviewDTO(
            review=ReviewDTO(
                id=2001,
                branch_id=100,
                content="제주 지점 좋았습니다.",
                branch_name="제주공항점",
                rating=4.5,
                created_at=datetime(2026, 2, 1, 10, 0, 0),
                car_model="아반떼",
            ),
            keywords=["좋았"],
            sentiment="positive",
            sentiment_score=0.8,
            tag_sentiments={
                "친절도": {"positive": ["좋았"], "negative": [], "neutral": []},
            },
        ),
        ProcessedReviewDTO(
            review=ReviewDTO(
                id=2002,
                branch_id=200,
                content="김포 지점도 만족합니다.",
                branch_name="김포공항점",
                rating=4.0,
                created_at=datetime(2026, 2, 2, 11, 0, 0),
                car_model="소나타",
            ),
            keywords=["만족"],
            sentiment="positive",
            sentiment_score=0.75,
            tag_sentiments={
                "친절도": {"positive": ["만족"], "negative": [], "neutral": []},
            },
        ),
    ]


# ==============================================================================
# Mock Supabase client fixture
# ==============================================================================


@pytest.fixture
def mock_supabase_client():
    """Mock Supabase AsyncClient (공통)

    table().select().eq().execute() 체인 및 upsert/update 모킹.
    개별 테스트에서 return value를 오버라이드 가능.
    """
    client = AsyncMock()

    # table().select().eq().execute() 체인 모킹
    mock_table = MagicMock()
    client.table.return_value = mock_table

    mock_select = MagicMock()
    mock_table.select.return_value = mock_select

    mock_eq = MagicMock()
    mock_select.eq.return_value = mock_eq
    mock_eq.eq.return_value = mock_eq
    mock_eq.in_.return_value = mock_eq
    mock_select.in_.return_value = mock_eq

    mock_execute = AsyncMock(return_value=MagicMock(data=[]))
    mock_eq.execute = mock_execute
    mock_eq.order.return_value = mock_eq
    mock_eq.limit.return_value = mock_eq

    # upsert 모킹
    mock_upsert = MagicMock()
    mock_table.upsert.return_value = mock_upsert
    mock_upsert.execute = AsyncMock(return_value=MagicMock(data=[{"id": 1}]))

    # update 모킹
    mock_update = MagicMock()
    mock_table.update.return_value = mock_update
    mock_update.eq.return_value = mock_update
    mock_update.execute = AsyncMock(return_value=MagicMock(data=[]))

    return client
