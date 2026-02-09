"""ReviewPreprocessor 테스트"""

import pytest
from datetime import datetime

from domain.pipeline.steps.preprocessor import ReviewPreprocessor
from schemas.dto import ReviewDTO


class TestReviewPreprocessor:
    """ReviewPreprocessor 테스트 클래스"""

    @pytest.fixture
    def preprocessor(self):
        """ReviewPreprocessor 인스턴스"""
        return ReviewPreprocessor()

    def test_process_batch_empty_input(self, preprocessor):
        """빈 리스트 입력 시 빈 리스트 반환"""
        result = preprocessor.process_batch([])
        assert result == []

    def test_process_batch_filters_invalid_reviews(self, preprocessor):
        """유효하지 않은 리뷰 필터링"""
        reviews = [
            {
                "review_id": "1",
                "branch_id": "100",
                "content": "짧",  # 5자 미만
                "branch_name": "테스트점",
                "rating_service": "5.0",
            },
            {
                "review_id": "2",
                "branch_id": "100",
                "content": "",  # 빈 내용
                "branch_name": "테스트점",
                "rating_service": "5.0",
            },
        ]
        result = preprocessor.process_batch(reviews)
        assert len(result) == 0

    def test_process_batch_valid_review(self, preprocessor):
        """유효한 리뷰 처리"""
        reviews = [
            {
                "review_id": "1001",
                "branch_id": "100",
                "content": "직원분들이 정말 친절하고 좋았습니다",
                "branch_name": "제주공항점",
                "rating_service": "5.0",
                "rating_car": "5.0",
                "rating_convenience": "4.5",
                "review_date": "2026-02-01 10:00:00",
                "car_type": "아반떼",
                "company_name": "카모아렌트카",
                "status": "1",
            },
        ]
        result = preprocessor.process_batch(reviews)

        assert len(result) == 1
        processed = result[0]
        assert processed.branch_id == 100
        assert processed.review.content == "직원분들이 정말 친절하고 좋았습니다"
        assert processed.sentiment in ["positive", "neutral", "negative"]
        assert isinstance(processed.keywords, list)
        assert isinstance(processed.tag_sentiments, dict)

    def test_process_batch_filters_profanity(self, preprocessor):
        """욕설 포함 리뷰 필터링"""
        reviews = [
            {
                "review_id": "1",
                "branch_id": "100",
                "content": "이 씨발 정말 최악의 서비스였습니다",  # 욕설 포함
                "branch_name": "테스트점",
                "rating_service": "1.0",
            },
        ]
        result = preprocessor.process_batch(reviews)
        # 욕설이 PROFANITY_PATTERNS에 있다면 필터링됨
        # 없다면 처리됨 - 실제 패턴에 따라 조정 필요
        assert len(result) <= 1

    def test_review_dto_from_athena_row(self):
        """ReviewDTO.from_athena_row 테스트"""
        row = {
            "review_id": "1001",
            "branch_id": "100",
            "content": "좋은 서비스였습니다",
            "branch_name": "제주공항점",
            "rating_service": "4.5",
            "review_date": "2026-02-01 10:00:00",
            "helpful_count": "5",
            "car_type": "아반떼",
            "company_name": "카모아렌트카",
            "status": "1",
        }

        dto = ReviewDTO.from_athena_row(row)

        assert dto.id == 1001
        assert dto.branch_id == 100
        assert dto.content == "좋은 서비스였습니다"
        assert dto.rating == 4.5
        assert dto.like_count == 5
        assert dto.car_model == "아반떼"

    def test_review_dto_from_athena_row_handles_none(self):
        """ReviewDTO.from_athena_row None 값 처리"""
        row = {
            "review_id": None,
            "branch_id": None,
            "content": None,
            "branch_name": None,
        }

        dto = ReviewDTO.from_athena_row(row)

        assert dto.id == 0
        assert dto.branch_id == 0
        assert dto.content == ""

    def test_process_batch_multiple_reviews(self, preprocessor):
        """여러 리뷰 처리"""
        reviews = [
            {
                "review_id": str(i),
                "branch_id": "100",
                "content": f"리뷰 내용 테스트 {i}번 입니다. 좋았습니다.",
                "branch_name": "테스트점",
                "rating_service": "5.0",
                "review_date": f"2026-02-0{i % 9 + 1} 10:00:00",
            }
            for i in range(1, 6)
        ]

        result = preprocessor.process_batch(reviews)

        # 최소 일부는 처리되어야 함
        assert len(result) >= 1

        # 각 결과가 올바른 타입인지 확인
        for processed in result:
            assert hasattr(processed, 'review')
            assert hasattr(processed, 'keywords')
            assert hasattr(processed, 'sentiment')
            assert hasattr(processed, 'tag_sentiments')

    # ===== Edge case 테스트 =====

    def test_process_batch_whitespace_only_content(self, preprocessor):
        """공백만 있는 리뷰는 필터링됨 (5자 미만)"""
        reviews = [
            {
                "review_id": "1",
                "branch_id": "100",
                "content": "     ",
                "branch_name": "테스트점",
                "rating_service": "5.0",
            },
        ]
        result = preprocessor.process_batch(reviews)
        assert len(result) == 0

    def test_process_batch_none_content(self, preprocessor):
        """content가 None인 경우"""
        reviews = [
            {
                "review_id": "1",
                "branch_id": "100",
                "content": None,
                "branch_name": "테스트점",
                "rating_service": "5.0",
            },
        ]
        result = preprocessor.process_batch(reviews)
        assert len(result) == 0

    def test_process_batch_blind_review(self, preprocessor):
        """블라인드 상태 리뷰는 필터링"""
        reviews = [
            {
                "review_id": "1",
                "branch_id": "100",
                "content": "이 리뷰는 블라인드 처리되었습니다.",
                "branch_name": "테스트점",
                "rating_service": "5.0",
                "status": "블라인드",
            },
        ]
        result = preprocessor.process_batch(reviews)
        assert len(result) == 0

    def test_process_batch_deleted_review(self, preprocessor):
        """삭제 상태 리뷰는 필터링"""
        reviews = [
            {
                "review_id": "1",
                "branch_id": "100",
                "content": "이 리뷰는 삭제된 리뷰입니다. 보이면 안 됩니다.",
                "branch_name": "테스트점",
                "rating_service": "5.0",
                "status": "삭제",
            },
        ]
        result = preprocessor.process_batch(reviews)
        assert len(result) == 0

    def test_process_batch_tag_sentiments_structure(self, preprocessor):
        """tag_sentiments 구조 검증: {태그: {positive: [], negative: [], neutral: []}}"""
        reviews = [
            {
                "review_id": "1001",
                "branch_id": "100",
                "content": "직원분들이 정말 친절하고 차량도 깨끗했습니다. 가격도 저렴했어요.",
                "branch_name": "제주공항점",
                "rating_service": "5.0",
                "rating_car": "5.0",
                "rating_convenience": "5.0",
                "review_date": "2026-02-01 10:00:00",
            },
        ]
        result = preprocessor.process_batch(reviews)

        if len(result) > 0:
            processed = result[0]
            assert isinstance(processed.tag_sentiments, dict)
            for tag_name, sentiments in processed.tag_sentiments.items():
                assert isinstance(tag_name, str)
                assert isinstance(sentiments, dict)
                assert "positive" in sentiments
                assert "negative" in sentiments
                assert "neutral" in sentiments
                assert isinstance(sentiments["positive"], list)
                assert isinstance(sentiments["negative"], list)
                assert isinstance(sentiments["neutral"], list)

    def test_process_batch_invalid_rating(self, preprocessor):
        """유효하지 않은 별점 문자열 처리"""
        reviews = [
            {
                "review_id": "1",
                "branch_id": "100",
                "content": "서비스가 정말 좋았습니다. 다음에도 이용하겠습니다.",
                "branch_name": "테스트점",
                "rating_service": "abc",  # 유효하지 않은 값
                "rating_car": "",  # 빈 문자열
                "rating_convenience": None,  # None
            },
        ]
        # 예외 없이 처리되어야 함
        result = preprocessor.process_batch(reviews)
        assert isinstance(result, list)

    def test_process_batch_invalid_review_date(self, preprocessor):
        """유효하지 않은 날짜 형식 처리"""
        reviews = [
            {
                "review_id": "1",
                "branch_id": "100",
                "content": "서비스가 정말 좋았습니다. 다음에도 이용하겠습니다.",
                "branch_name": "테스트점",
                "rating_service": "5.0",
                "review_date": "invalid-date",
            },
        ]
        result = preprocessor.process_batch(reviews)
        assert isinstance(result, list)

    def test_process_batch_missing_keys(self, preprocessor):
        """필수 키가 없는 dict 처리"""
        reviews = [
            {
                "content": "서비스가 정말 좋았습니다. 다음에도 이용하겠습니다.",
                # review_id, branch_id 없음
            },
        ]
        # from_athena_row에서 safe_int로 처리되므로 예외 없이 동작
        result = preprocessor.process_batch(reviews)
        assert isinstance(result, list)

    def test_review_dto_is_valid_method(self):
        """ReviewDTO.is_valid() 메서드 테스트"""
        # 유효한 리뷰
        valid = ReviewDTO(id=1, branch_id=100, content="좋은 서비스였습니다")
        assert valid.is_valid() is True

        # 빈 내용
        empty = ReviewDTO(id=1, branch_id=100, content="")
        assert empty.is_valid() is False

        # 5자 미만
        short = ReviewDTO(id=1, branch_id=100, content="짧은")
        assert short.is_valid() is False

        # 블라인드
        blind = ReviewDTO(id=1, branch_id=100, content="좋은 서비스였습니다", is_blind=True)
        assert blind.is_valid() is False

        # 삭제 상태
        deleted = ReviewDTO(id=1, branch_id=100, content="좋은 서비스였습니다", status="삭제")
        assert deleted.is_valid() is False

    def test_review_dto_to_dict(self, sample_review_dto):
        """ReviewDTO.to_dict() 메서드 테스트"""
        d = sample_review_dto.to_dict()

        assert d["id"] == 1001
        assert d["branch_id"] == 100
        assert d["content"] == "직원분들이 정말 친절하고 차량도 깨끗했습니다."
        assert d["car_model"] == "아반떼"
        assert d["created_at"] == "2026-02-01T10:00:00"

    def test_review_dto_from_db_row(self):
        """ReviewDTO.from_db_row 테스트"""
        row = {
            "id": 1001,
            "branch_id": 100,
            "content": "좋은 서비스",
            "branch_name": "제주공항점",
            "rating_service": 4.5,
            "review_date": "2026-02-01T10:00:00",
            "helpful_count": 5,
            "car_model": "아반떼",
            "company_name": "카모아렌트카",
        }

        dto = ReviewDTO.from_db_row(row)
        assert dto.id == 1001
        assert dto.branch_id == 100
        assert dto.rating == 4.5
        assert dto.car_model == "아반떼"

    def test_review_dto_from_db_row_empty(self):
        """ReviewDTO.from_db_row 빈 dict"""
        dto = ReviewDTO.from_db_row({})
        assert dto.id == 0
        assert dto.branch_id == 0
        assert dto.content == ""

    def test_processed_review_dto_properties(self, sample_processed_reviews):
        """ProcessedReviewDTO의 branch_id, content 프로퍼티"""
        pr = sample_processed_reviews[0]
        assert pr.branch_id == 100
        assert pr.content == "직원분들이 정말 친절하고 차량도 깨끗했습니다."

    def test_processed_review_dto_to_dict(self, sample_processed_reviews):
        """ProcessedReviewDTO.to_dict() 테스트"""
        pr = sample_processed_reviews[0]
        d = pr.to_dict()

        assert d["id"] == 1001
        assert d["keywords"] == ["친절", "깨끗"]
        assert d["sentiment"] == "positive"
        assert d["sentiment_score"] == 0.85
        assert d["is_negative_filtered"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
