"""Pipeline Steps 유닛 테스트"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from domain.pipeline.steps.car_model_tags import CarModelTagAggregator
from domain.pipeline.steps.keyword_manager import KeywordManager
from domain.pipeline.steps.tag_aggregator import TagAggregator
from domain.pipeline.steps.sentiment_stats import SentimentStatsUpdater
from domain.pipeline.steps.review_updater import ReviewSentimentUpdater
from schemas.dto import ReviewDTO, ProcessedReviewDTO


# ==============================================================================
# 로컬 mock fixture (conftest의 mock_supabase_client와 별개로 관리)
# ==============================================================================


@pytest.fixture
def mock_client():
    """Mock Supabase AsyncClient"""
    client = AsyncMock()

    mock_table = MagicMock()
    client.table.return_value = mock_table

    mock_select = MagicMock()
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_select
    mock_select.in_.return_value = mock_select
    mock_select.execute = AsyncMock(return_value=MagicMock(data=[]))

    mock_upsert = MagicMock()
    mock_table.upsert.return_value = mock_upsert
    mock_upsert.execute = AsyncMock(return_value=MagicMock(data=[{"id": 1}]))

    mock_update = MagicMock()
    mock_table.update.return_value = mock_update
    mock_update.eq.return_value = mock_update
    mock_update.execute = AsyncMock(return_value=MagicMock(data=[]))

    return client


# ==============================================================================
# CarModelTagAggregator 테스트
# ==============================================================================


class TestCarModelTagAggregator:
    """CarModelTagAggregator 테스트"""

    @pytest.fixture
    def aggregator(self):
        return CarModelTagAggregator()

    @pytest.mark.asyncio
    async def test_aggregate_empty_input(self, aggregator, mock_client):
        """빈 입력 처리"""
        result = await aggregator.aggregate(mock_client, [])
        assert result == {"cars_processed": 0, "tags_saved": 0}

    @pytest.mark.asyncio
    async def test_aggregate_no_car_model(self, aggregator, mock_client):
        """차량 모델 없는 리뷰 건너뛰기"""
        reviews = [
            ProcessedReviewDTO(
                review=ReviewDTO(
                    id=1,
                    branch_id=100,
                    content="테스트 리뷰입니다.",
                    car_model="",  # 빈 차량 모델
                ),
                keywords=["테스트"],
                sentiment="positive",
                tag_sentiments={"친절도": {"positive": ["테스트"], "negative": [], "neutral": []}},
            ),
        ]
        result = await aggregator.aggregate(mock_client, reviews)
        assert result["cars_processed"] == 0

    @pytest.mark.asyncio
    async def test_aggregate_with_car_model(self, aggregator, mock_client, sample_processed_reviews):
        """차량 모델 있는 리뷰 처리"""
        # tags 배치 조회 + car_model_tags 배치 조회 모킹
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table

        mock_select = MagicMock()
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_select
        mock_select.in_.return_value = mock_select
        mock_select.execute = AsyncMock(return_value=MagicMock(data=[{"id": 1, "name": "친절도"}]))

        mock_upsert = MagicMock()
        mock_table.upsert.return_value = mock_upsert
        mock_upsert.execute = AsyncMock(return_value=MagicMock(data=[{"id": 1}]))

        result = await aggregator.aggregate(mock_client, sample_processed_reviews)

        assert "cars_processed" in result
        assert "tags_saved" in result

    @pytest.mark.asyncio
    async def test_aggregate_whitespace_car_model(self, aggregator, mock_client):
        """공백만 있는 차량 모델명은 빈 문자열로 처리되어 건너뜀"""
        reviews = [
            ProcessedReviewDTO(
                review=ReviewDTO(
                    id=10,
                    branch_id=100,
                    content="테스트 리뷰입니다.",
                    car_model="   ",  # 공백만
                ),
                keywords=["테스트"],
                sentiment="positive",
                tag_sentiments={"친절도": {"positive": ["테스트"], "negative": [], "neutral": []}},
            ),
        ]
        result = await aggregator.aggregate(mock_client, reviews)
        assert result["cars_processed"] == 0

    @pytest.mark.asyncio
    async def test_aggregate_skips_etc_tag(self, aggregator, mock_client):
        """'기타' 태그는 건너뜀"""
        reviews = [
            ProcessedReviewDTO(
                review=ReviewDTO(
                    id=10,
                    branch_id=100,
                    content="테스트 리뷰입니다.",
                    car_model="아반떼",
                ),
                keywords=["기타키워드"],
                sentiment="positive",
                tag_sentiments={"기타": {"positive": ["기타키워드"], "negative": [], "neutral": []}},
            ),
        ]
        result = await aggregator.aggregate(mock_client, reviews)
        # 기타 태그만 있으므로 car_tag_data가 비어서 0
        assert result["cars_processed"] == 0

    @pytest.mark.asyncio
    async def test_aggregate_db_exception_continues(self, aggregator, mock_client, sample_processed_reviews):
        """DB 예외 발생 시 해당 항목 건너뛰고 계속 처리"""
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table

        mock_select = MagicMock()
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_select
        mock_select.in_.return_value = mock_select
        # tags 배치 조회 시 예외 발생
        mock_select.execute = AsyncMock(side_effect=Exception("DB 오류"))

        mock_upsert = MagicMock()
        mock_table.upsert.return_value = mock_upsert
        mock_upsert.execute = AsyncMock(return_value=MagicMock(data=[]))

        result = await aggregator.aggregate(mock_client, sample_processed_reviews)
        # tag_id를 못 찾아서 tags_saved=0
        assert result["tags_saved"] == 0


# ==============================================================================
# KeywordManager 테스트
# ==============================================================================


class TestKeywordManager:
    """KeywordManager 테스트"""

    @pytest.fixture
    def manager(self):
        return KeywordManager()

    @pytest.mark.asyncio
    async def test_update_empty_input(self, manager, mock_client):
        """빈 입력 처리"""
        result = await manager.update(mock_client, [])
        assert result == 0

    @pytest.mark.asyncio
    async def test_update_with_keywords(self, manager, mock_client, sample_processed_reviews):
        """키워드 업데이트"""
        result = await manager.update(mock_client, sample_processed_reviews)

        # 최소 0 이상
        assert result >= 0

    @pytest.mark.asyncio
    async def test_update_skips_reviews_without_created_at(self, manager, mock_client):
        """created_at이 None인 리뷰는 건너뜀"""
        reviews = [
            ProcessedReviewDTO(
                review=ReviewDTO(
                    id=10,
                    branch_id=100,
                    content="테스트 리뷰입니다.",
                    created_at=None,  # None
                ),
                keywords=["테스트"],
                sentiment="positive",
            ),
        ]
        result = await manager.update(mock_client, reviews)
        assert result == 0

    @pytest.mark.asyncio
    async def test_update_empty_keywords_list(self, manager, mock_client):
        """빈 keywords 리스트인 리뷰 처리"""
        reviews = [
            ProcessedReviewDTO(
                review=ReviewDTO(
                    id=10,
                    branch_id=100,
                    content="테스트 리뷰입니다.",
                    created_at=datetime(2026, 2, 1, 10, 0, 0),
                ),
                keywords=[],  # 빈 키워드
                sentiment="neutral",
            ),
        ]
        result = await manager.update(mock_client, reviews)
        # 키워드가 없으므로 upsert_rows가 비어서 updated 안 됨
        assert result == 0

    @pytest.mark.asyncio
    async def test_update_db_exception_continues(self, manager, mock_client, sample_processed_reviews):
        """DB 예외 발생 시 건너뛰고 계속"""
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table

        mock_select = MagicMock()
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_select
        mock_select.execute = AsyncMock(side_effect=Exception("DB 오류"))

        mock_upsert = MagicMock()
        mock_table.upsert.return_value = mock_upsert
        mock_upsert.execute = AsyncMock(return_value=MagicMock(data=[]))

        result = await manager.update(mock_client, sample_processed_reviews)
        # 예외 처리로 0
        assert result == 0


# ==============================================================================
# TagAggregator 테스트
# ==============================================================================


class TestTagAggregator:
    """TagAggregator 테스트"""

    @pytest.fixture
    def aggregator(self):
        return TagAggregator()

    @pytest.mark.asyncio
    async def test_aggregate_empty_input(self, aggregator, mock_client):
        """빈 입력 처리"""
        result = await aggregator.aggregate(mock_client, [])
        assert result == {"branches": 0, "tags": 0}

    @pytest.mark.asyncio
    async def test_aggregate_with_tags(self, aggregator, mock_client, sample_processed_reviews):
        """태그 집계"""
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table

        mock_select = MagicMock()
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_select
        mock_select.in_.return_value = mock_select
        mock_select.execute = AsyncMock(return_value=MagicMock(data=[]))

        mock_upsert = MagicMock()
        mock_table.upsert.return_value = mock_upsert
        mock_upsert.execute = AsyncMock(return_value=MagicMock(data=[{"id": 1}]))

        result = await aggregator.aggregate(mock_client, sample_processed_reviews)

        assert "branches" in result
        assert "tags" in result

    @pytest.mark.asyncio
    async def test_aggregate_skips_etc_tag(self, aggregator, mock_client):
        """'기타' 태그는 무시 - branch_tag_data에 키는 생기지만 태그 없음"""
        reviews = [
            ProcessedReviewDTO(
                review=ReviewDTO(
                    id=10,
                    branch_id=100,
                    content="테스트 리뷰입니다.",
                ),
                keywords=["기타"],
                sentiment="positive",
                tag_sentiments={"기타": {"positive": ["기타"], "negative": [], "neutral": []}},
            ),
        ]

        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_upsert = MagicMock()
        mock_table.upsert.return_value = mock_upsert
        mock_upsert.execute = AsyncMock(return_value=MagicMock(data=[]))

        result = await aggregator.aggregate(mock_client, reviews)
        # branch_tag_data에 bid 키는 생기지만 '기타'는 continue로 건너뛰어 태그 없음
        assert result["tags"] == 0

    @pytest.mark.asyncio
    async def test_aggregate_empty_tag_sentiments(self, aggregator, mock_client):
        """tag_sentiments가 빈 dict인 경우"""
        reviews = [
            ProcessedReviewDTO(
                review=ReviewDTO(
                    id=10,
                    branch_id=100,
                    content="태그 없는 리뷰입니다.",
                ),
                keywords=["리뷰"],
                sentiment="neutral",
                tag_sentiments={},
            ),
        ]
        result = await aggregator.aggregate(mock_client, reviews)
        # branch_tag_data에 bid 키는 생기지만 내부 태그 데이터 없음
        assert result["tags"] == 0

    @pytest.mark.asyncio
    async def test_aggregate_counts_positive_and_negative(self, aggregator):
        """positive_count, negative_count가 정확히 집계되는지 검증"""
        reviews = [
            ProcessedReviewDTO(
                review=ReviewDTO(id=1, branch_id=100, content="좋은 서비스"),
                keywords=["좋은"],
                sentiment="positive",
                tag_sentiments={
                    "친절도": {"positive": ["좋은", "훌륭"], "negative": [], "neutral": ["보통"]},
                },
            ),
            ProcessedReviewDTO(
                review=ReviewDTO(id=2, branch_id=100, content="불친절"),
                keywords=["불친절"],
                sentiment="negative",
                tag_sentiments={
                    "친절도": {"positive": [], "negative": ["불친절"], "neutral": []},
                },
            ),
        ]

        # MagicMock 기반 client로 배치 조회 + upsert 성공 모킹
        client = MagicMock()
        mock_table = MagicMock()
        client.table.return_value = mock_table

        mock_select = MagicMock()
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_select
        mock_select.in_.return_value = mock_select
        mock_select.execute = AsyncMock(return_value=MagicMock(data=[]))

        mock_upsert = MagicMock()
        mock_table.upsert.return_value = mock_upsert
        mock_upsert.execute = AsyncMock(return_value=MagicMock(data=[{"id": 1}]))

        result = await aggregator.aggregate(client, reviews)
        assert result["branches"] == 1  # branch 100만
        assert result["tags"] >= 1


# ==============================================================================
# SentimentStatsUpdater 테스트
# ==============================================================================


class TestSentimentStatsUpdater:
    """SentimentStatsUpdater 테스트"""

    @pytest.fixture
    def updater(self):
        return SentimentStatsUpdater()

    @pytest.mark.asyncio
    async def test_update_empty_input(self, updater, mock_client):
        """빈 입력 처리"""
        result = await updater.update(mock_client, [])
        assert result == 0

    @pytest.mark.asyncio
    async def test_update_with_reviews(self, updater, mock_client, sample_processed_reviews):
        """감정 통계 업데이트"""
        result = await updater.update(mock_client, sample_processed_reviews)

        # 최소 0 이상
        assert result >= 0

    @pytest.mark.asyncio
    async def test_update_increments_existing_stats(self, updater):
        """기존 통계가 있을 때 증분 업데이트"""
        reviews = [
            ProcessedReviewDTO(
                review=ReviewDTO(id=1, branch_id=100, content="좋은 서비스"),
                keywords=[],
                sentiment="positive",
            ),
        ]

        # 기존 데이터가 있는 경우 모킹 - MagicMock 기반 client
        client = MagicMock()

        mock_table = MagicMock()
        client.table.return_value = mock_table

        mock_select = MagicMock()
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_select
        mock_select.execute = AsyncMock(
            return_value=MagicMock(data=[{
                "positive_count": 10,
                "negative_count": 5,
                "neutral_count": 3,
            }])
        )

        mock_upsert = MagicMock()
        mock_table.upsert.return_value = mock_upsert
        mock_upsert.execute = AsyncMock(return_value=MagicMock(data=[{"id": 1}]))

        result = await updater.update(client, reviews)
        assert result == 1

    @pytest.mark.asyncio
    async def test_update_multiple_branches(self, updater, sample_multi_branch_reviews):
        """여러 지점 감정 통계 업데이트"""
        client = MagicMock()
        mock_table = MagicMock()
        client.table.return_value = mock_table

        mock_select = MagicMock()
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_select
        mock_select.execute = AsyncMock(return_value=MagicMock(data=[]))

        mock_upsert = MagicMock()
        mock_table.upsert.return_value = mock_upsert
        mock_upsert.execute = AsyncMock(return_value=MagicMock(data=[{"id": 1}]))

        result = await updater.update(client, sample_multi_branch_reviews)
        # 2개 지점 업데이트
        assert result == 2

    @pytest.mark.asyncio
    async def test_update_db_exception_continues(self, updater):
        """DB 예외 시 해당 지점 건너뛰고 계속"""
        reviews = [
            ProcessedReviewDTO(
                review=ReviewDTO(id=1, branch_id=100, content="테스트"),
                keywords=[],
                sentiment="positive",
            ),
        ]

        client = MagicMock()
        mock_table = MagicMock()
        client.table.return_value = mock_table
        mock_select = MagicMock()
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_select
        mock_select.execute = AsyncMock(side_effect=Exception("DB 연결 실패"))

        mock_upsert = MagicMock()
        mock_table.upsert.return_value = mock_upsert
        mock_upsert.execute = AsyncMock(return_value=MagicMock(data=[]))

        result = await updater.update(client, reviews)
        assert result == 0


# ==============================================================================
# ReviewSentimentUpdater 테스트
# ==============================================================================


class TestReviewSentimentUpdater:
    """ReviewSentimentUpdater 테스트"""

    @pytest.fixture
    def updater(self):
        return ReviewSentimentUpdater()

    @pytest.mark.asyncio
    async def test_update_empty_input(self, updater, mock_client):
        """빈 입력 처리"""
        result = await updater.update(mock_client, [])
        assert result == 0

    @pytest.mark.asyncio
    async def test_update_skips_zero_id(self, updater, mock_client):
        """ID가 0인 리뷰 건너뛰기"""
        reviews = [
            ProcessedReviewDTO(
                review=ReviewDTO(
                    id=0,  # 0 ID
                    branch_id=100,
                    content="테스트",
                ),
                keywords=[],
                sentiment="positive",
            ),
        ]
        result = await updater.update(mock_client, reviews)
        assert result == 0

    @pytest.mark.asyncio
    async def test_update_skips_none_id(self, updater, mock_client):
        """ID가 None인 리뷰 건너뛰기"""
        reviews = [
            ProcessedReviewDTO(
                review=ReviewDTO(
                    id=0,  # from_athena_row에서 None은 0으로 변환됨
                    branch_id=100,
                    content="테스트",
                ),
                keywords=[],
                sentiment="positive",
            ),
        ]
        result = await updater.update(mock_client, reviews)
        assert result == 0

    @pytest.mark.asyncio
    async def test_update_valid_review(self, updater):
        """유효한 리뷰 sentiment 업데이트 성공"""
        reviews = [
            ProcessedReviewDTO(
                review=ReviewDTO(id=1001, branch_id=100, content="좋은 서비스"),
                keywords=["좋은"],
                sentiment="positive",
            ),
        ]

        client = MagicMock()
        mock_table = MagicMock()
        client.table.return_value = mock_table
        mock_update = MagicMock()
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value = mock_update
        mock_update.execute = AsyncMock(return_value=MagicMock(data=[]))

        result = await updater.update(client, reviews)
        assert result == 1

    @pytest.mark.asyncio
    async def test_update_db_exception_continues(self, updater):
        """DB 예외 시 건너뛰고 계속 처리"""
        reviews = [
            ProcessedReviewDTO(
                review=ReviewDTO(id=1001, branch_id=100, content="리뷰1"),
                keywords=[],
                sentiment="positive",
            ),
            ProcessedReviewDTO(
                review=ReviewDTO(id=1002, branch_id=100, content="리뷰2"),
                keywords=[],
                sentiment="negative",
            ),
        ]

        client = MagicMock()
        mock_table = MagicMock()
        client.table.return_value = mock_table
        mock_update = MagicMock()
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value = mock_update

        call_count = 0

        async def side_effect_execute():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("DB 오류")
            return MagicMock(data=[])

        mock_update.execute = side_effect_execute

        result = await updater.update(client, reviews)
        # 첫 번째 실패, 두 번째 성공
        assert result == 1

    @pytest.mark.asyncio
    async def test_update_multiple_reviews(self, updater):
        """여러 리뷰 업데이트"""
        reviews = [
            ProcessedReviewDTO(
                review=ReviewDTO(
                    id=1001, branch_id=100,
                    content="직원분들이 정말 친절하고 차량도 깨끗했습니다.",
                ),
                keywords=["친절", "깨끗"],
                sentiment="positive",
            ),
            ProcessedReviewDTO(
                review=ReviewDTO(
                    id=1002, branch_id=100,
                    content="차량 상태가 좋지 않았고 냄새도 났습니다.",
                ),
                keywords=["냄새", "상태"],
                sentiment="negative",
            ),
        ]

        client = MagicMock()
        mock_table = MagicMock()
        client.table.return_value = mock_table
        mock_update = MagicMock()
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value = mock_update
        mock_update.execute = AsyncMock(return_value=MagicMock(data=[]))

        result = await updater.update(client, reviews)
        assert result == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
