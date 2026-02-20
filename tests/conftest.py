"""테스트 공통 설정 및 픽스처"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# app 디렉토리를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))


# ============================================================
# 공통 Mock 픽스처
# ============================================================


class FakeBranchTag:
    """branch_tag_repo.get_by_branch() 결과 모킹용"""

    def __init__(self, name: str, category: str, pos: int, neg: int, neu: int = 0):
        self.positive_count = pos
        self.negative_count = neg
        self.neutral_count = neu
        self._name = name
        self._category = category

    def model_dump(self):
        return {
            "tags": {
                "name": self._name,
                "categories": {"name": self._category},
            }
        }


@pytest.fixture
def sample_branch_tags():
    """테스트용 branch_tag 데이터"""
    return [
        FakeBranchTag("친절한 직원", "서비스", pos=80, neg=5, neu=10),
        FakeBranchTag("깨끗한 차량", "청결", pos=60, neg=20, neu=5),
        FakeBranchTag("비싼 가격", "가격", pos=5, neg=50, neu=10),
        FakeBranchTag("빠른 출고", "서비스", pos=40, neg=3, neu=2),
        FakeBranchTag("냄새", "청결", pos=2, neg=30, neu=5),
    ]


@pytest.fixture
def mock_branch_tag_repo(sample_branch_tags):
    repo = AsyncMock()
    repo.get_by_branch = AsyncMock(return_value=sample_branch_tags)
    return repo


@pytest.fixture
def mock_summary_repo():
    repo = AsyncMock()
    summary = MagicMock()
    summary.model_dump.return_value = {
        "branch_name": "테스트지점",
        "affiliate_name": "테스트업체",
        "review_count": 150,
        "region": "서울",
    }
    summary.region = "서울"
    repo.get_by_branch_id = AsyncMock(return_value=summary)
    return repo


@pytest.fixture
def mock_review_repo():
    repo = AsyncMock()
    repo.count_by_branch = AsyncMock(return_value=150)
    repo.get_by_branch = AsyncMock(return_value=MagicMock(reviews=[
        {"content": "직원이 친절했어요"},
        {"content": "차가 깨끗했습니다"},
        {"content": "가격이 좀 비싸요"},
    ]))
    return repo


@pytest.fixture
def mock_report_repo():
    repo = AsyncMock()
    repo.get_by_branch_and_period = AsyncMock(return_value=None)
    repo.get_all_by_branch = AsyncMock(return_value=[])
    repo.save = AsyncMock()
    return repo


@pytest.fixture
def mock_sentiment_repo():
    return AsyncMock()
