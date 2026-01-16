"""
Container 단위 테스트

구현 일지:
- 2026-01-16: 초기 테스트 작성
"""
import pytest
import sys
import os

# 프로젝트 루트 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.dto import PipelineConfigDTO
from src.container import Container, get_container, reset_container


class TestContainer:
    """Container 테스트"""
    
    def test_create_container(self):
        """Container 생성 테스트"""
        config = PipelineConfigDTO()
        container = Container(config)
        
        assert container.config is not None
        assert container.config.min_reviews == 30
    
    def test_lazy_loading(self):
        """지연 로딩 테스트"""
        container = Container(PipelineConfigDTO())
        
        # 초기 상태: 아무것도 초기화 안됨
        assert container._sentiment_analyzer is None
        assert container._keyword_extractor is None
        
        # 접근하면 초기화됨
        extractor = container.keyword_extractor
        assert extractor is not None
        assert container._initialized['keyword_extractor'] is True
    
    def test_override(self):
        """의존성 오버라이드 테스트"""
        container = Container(PipelineConfigDTO())
        
        # Mock 객체
        class MockAnalyzer:
            def analyze(self, text):
                return {'mock': True}
        
        container.override(sentiment_analyzer=MockAnalyzer())
        
        assert container._initialized['sentiment_analyzer'] is True
        assert hasattr(container.sentiment_analyzer, 'analyze')
    
    def test_reset(self):
        """캐시 초기화 테스트"""
        container = Container(PipelineConfigDTO())
        
        # 키워드 추출기 초기화
        _ = container.keyword_extractor
        assert container._initialized['keyword_extractor'] is True
        
        # 리셋
        container.reset()
        assert container._initialized['keyword_extractor'] is False
    
    def test_initialization_status(self):
        """초기화 상태 확인 테스트"""
        container = Container(PipelineConfigDTO())
        
        status = container.get_initialization_status()
        assert all(v is False for v in status.values())


class TestGetContainer:
    """get_container 함수 테스트"""
    
    def setup_method(self):
        """각 테스트 전 초기화"""
        reset_container()
    
    def test_singleton_pattern(self):
        """싱글톤 패턴 테스트"""
        container1 = get_container()
        container2 = get_container()
        
        assert container1 is container2
    
    def test_new_container_with_config(self):
        """새 설정으로 Container 생성"""
        config = PipelineConfigDTO(min_reviews=100)
        container = get_container(config)
        
        assert container.config.min_reviews == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
