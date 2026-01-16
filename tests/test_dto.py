"""
DTO 및 Container 단위 테스트

구현 일지:
- 2026-01-16: 초기 테스트 작성
"""
import pytest
import sys
import os

# 프로젝트 루트 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.dto import (
    ReviewDTO,
    SentimentDTO,
    SummaryRequestDTO,
    SummaryResponseDTO,
    PipelineConfigDTO,
    PipelineStepResultDTO,
    PipelineResultDTO,
)


class TestReviewDTO:
    """ReviewDTO 테스트"""
    
    def test_create_review(self):
        """리뷰 생성 테스트"""
        review = ReviewDTO(
            id=1,
            branch_id=101,
            content="서비스가 정말 좋았습니다!"
        )
        assert review.id == 1
        assert review.branch_id == 101
        assert "서비스" in review.content
    
    def test_is_valid_true(self):
        """유효한 리뷰 테스트"""
        review = ReviewDTO(id=1, branch_id=101, content="좋은 서비스였습니다")
        assert review.is_valid() is True
    
    def test_is_valid_false_short(self):
        """짧은 리뷰는 무효"""
        review = ReviewDTO(id=1, branch_id=101, content="좋아")
        assert review.is_valid() is False
    
    def test_is_valid_false_blind(self):
        """블라인드 리뷰는 무효"""
        review = ReviewDTO(id=1, branch_id=101, content="좋은 서비스였습니다", is_blind=True)
        assert review.is_valid() is False
    
    def test_to_dict(self):
        """딕셔너리 변환 테스트"""
        review = ReviewDTO(id=1, branch_id=101, content="테스트")
        d = review.to_dict()
        assert d['id'] == 1
        assert d['branch_id'] == 101


class TestSentimentDTO:
    """SentimentDTO 테스트"""
    
    def test_positive_sentiment(self):
        """긍정 감정 테스트"""
        sentiment = SentimentDTO(
            sentiment='positive',
            score=0.85,
            method='hybrid'
        )
        assert sentiment.is_positive is True
        assert sentiment.is_confident is True
    
    def test_negative_sentiment(self):
        """부정 감정 테스트"""
        sentiment = SentimentDTO(
            sentiment='negative',
            score=0.2,
            method='lexicon'
        )
        assert sentiment.is_positive is False
        assert sentiment.is_confident is True
    
    def test_neutral_not_confident(self):
        """중립 (애매한) 감정 테스트"""
        sentiment = SentimentDTO(
            sentiment='neutral',
            score=0.5,
            method='bert'
        )
        assert sentiment.is_confident is False


class TestSummaryRequestDTO:
    """SummaryRequestDTO 테스트"""
    
    def test_to_prompt_context(self):
        """프롬프트 컨텍스트 생성 테스트"""
        request = SummaryRequestDTO(
            branch_id=101,
            branch_name="강남점",
            keywords=["친절", "서비스", "깨끗"],
            representative_reviews=["정말 좋았어요"],
            review_count=150,
            avg_sentiment_score=0.75
        )
        context = request.to_prompt_context()
        assert "강남점" in context
        assert "친절" in context
        assert "150" in context


class TestPipelineConfigDTO:
    """PipelineConfigDTO 테스트"""
    
    def test_default_values(self):
        """기본값 테스트"""
        config = PipelineConfigDTO()
        assert config.min_reviews == 30
        assert config.sentiment_threshold == 0.45
        assert config.use_bert is True
    
    def test_custom_values(self):
        """커스텀 값 테스트"""
        config = PipelineConfigDTO(min_reviews=50, use_bert=False)
        assert config.min_reviews == 50
        assert config.use_bert is False


class TestPipelineResultDTO:
    """PipelineResultDTO 테스트"""
    
    def test_add_step(self):
        """스텝 추가 테스트"""
        result = PipelineResultDTO(
            success=True,
            total_reviews=1000,
            processed_reviews=800,
            total_branches=50,
            summaries_generated=50
        )
        
        step = PipelineStepResultDTO(
            step_name="load_data",
            success=True,
            input_count=0,
            output_count=1000,
            duration_seconds=1.5
        )
        result.add_step(step)
        
        assert len(result.steps) == 1
        assert result.steps[0].step_name == "load_data"
    
    def test_failed_steps(self):
        """실패 스텝 추적 테스트"""
        result = PipelineResultDTO(
            success=False,
            total_reviews=1000,
            processed_reviews=0,
            total_branches=0,
            summaries_generated=0
        )
        
        result.add_step(PipelineStepResultDTO("step1", True, 100, 100))
        result.add_step(PipelineStepResultDTO("step2", False, 100, 0, error_message="Error"))
        
        assert result.failed_steps == ["step2"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
