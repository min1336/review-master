"""
DI Container (Dependency Injection Container)

모든 의존성을 한 곳에서 관리하고, 레고 블록처럼 조합할 수 있게 합니다.

구현 일지:
- 2026-01-16: Container 클래스 생성 - 지연 로딩(Lazy Loading) 패턴 적용

사용법:
    >>> from src.container import Container
    >>> from src.dto import PipelineConfigDTO
    >>> 
    >>> config = PipelineConfigDTO()
    >>> container = Container(config)
    >>> 
    >>> # 필요할 때 자동 생성됨 (지연 로딩)
    >>> analyzer = container.sentiment_analyzer
    >>> extractor = container.keyword_extractor
"""
from dataclasses import dataclass
from typing import Optional, Any
import os

from ..dto import PipelineConfigDTO


class Container:
    """
    DI 컨테이너 - 모든 의존성을 조합
    
    지연 로딩(Lazy Loading) 패턴을 사용하여 필요할 때만 객체를 생성합니다.
    테스트 시 Mock 객체를 주입할 수 있습니다.
    
    Example:
        >>> # 기본 사용
        >>> container = Container(PipelineConfigDTO())
        >>> 
        >>> # Mock 주입 (테스트용)
        >>> container = Container(config)
        >>> container._sentiment_analyzer = MockAnalyzer()
    """
    
    def __init__(self, config: PipelineConfigDTO = None):
        """
        Args:
            config: 파이프라인 설정. None이면 기본값 사용.
        """
        self.config = config or PipelineConfigDTO()
        
        # 캐시된 인스턴스 (지연 로딩)
        self._sentiment_analyzer = None
        self._keyword_extractor = None
        self._keyword_aggregator = None
        self._weight_calculator = None
        self._llm_provider = None
        
        # 초기화 상태 추적
        self._initialized = {
            'sentiment_analyzer': False,
            'keyword_extractor': False,
            'keyword_aggregator': False,
            'weight_calculator': False,
            'llm_provider': False,
        }
    
    # ==========================================================================
    # 감정분석 모듈
    # ==========================================================================
    
    @property
    def sentiment_analyzer(self):
        """
        하이브리드 감정분석기 (Lexicon + BERT)
        
        Returns:
            HybridSentimentAnalyzer 인스턴스
        """
        if self._sentiment_analyzer is None:
            from ..analysis.sentiment import HybridSentimentAnalyzer
            self._sentiment_analyzer = HybridSentimentAnalyzer(
                use_bert=self.config.use_bert,
                confident_high=self.config.confident_high,
                confident_low=self.config.confident_low
            )
            self._initialized['sentiment_analyzer'] = True
            print(f"✅ 감정분석기 초기화 완료 (BERT: {self.config.use_bert})")
        return self._sentiment_analyzer
    
    # ==========================================================================
    # 키워드 추출 모듈
    # ==========================================================================
    
    @property
    def keyword_extractor(self):
        """
        키워드 추출기 (MeCab 기반)
        
        Returns:
            KeywordExtractor 인스턴스
        """
        if self._keyword_extractor is None:
            from ..analysis.keywords import KeywordExtractor
            self._keyword_extractor = KeywordExtractor()
            self._initialized['keyword_extractor'] = True
            print("✅ 키워드 추출기 초기화 완료")
        return self._keyword_extractor
    
    @property
    def weight_calculator(self):
        """
        가중치 계산기
        
        Returns:
            WeightCalculator 인스턴스
        """
        if self._weight_calculator is None:
            from ..analysis.keywords import WeightCalculator
            self._weight_calculator = WeightCalculator()
            self._initialized['weight_calculator'] = True
            print("✅ 가중치 계산기 초기화 완료")
        return self._weight_calculator
    
    @property
    def keyword_aggregator(self):
        """
        키워드 집계기 (extractor + weight_calculator 조합)
        
        Returns:
            KeywordAggregator 인스턴스
        """
        if self._keyword_aggregator is None:
            from ..analysis.keywords import KeywordAggregator
            self._keyword_aggregator = KeywordAggregator(
                extractor=self.keyword_extractor,
                weight_calculator=self.weight_calculator,
                use_weights=self.config.use_keyword_weights
            )
            self._initialized['keyword_aggregator'] = True
            print("✅ 키워드 집계기 초기화 완료")
        return self._keyword_aggregator
    
    # ==========================================================================
    # LLM 모듈
    # ==========================================================================
    
    @property
    def llm_provider(self):
        """
        LLM Provider (OpenAI 또는 Gemini)
        
        환경변수 LLM_PROVIDER 또는 config.llm_provider에 따라 결정됩니다.
        
        Returns:
            LLMProvider 인스턴스
        """
        if self._llm_provider is None:
            # 환경변수에서 Provider 설정 확인
            provider_type = os.getenv('LLM_PROVIDER', self.config.llm_provider).lower()
            
            if provider_type == 'openai':
                api_key = os.getenv('OPENAI_API_KEY')
                if api_key:
                    from ..llm import OpenAIProvider
                    self._llm_provider = OpenAIProvider(api_key=api_key)
                    self._initialized['llm_provider'] = True
                    print(f"✅ OpenAI Provider 초기화 완료")
                else:
                    print("⚠️ OPENAI_API_KEY 환경변수 필요")
                    
            elif provider_type == 'gemini':
                api_key = os.getenv('GEMINI_API_KEY')
                if api_key:
                    from ..llm import GeminiProvider
                    self._llm_provider = GeminiProvider(api_key=api_key)
                    self._initialized['llm_provider'] = True
                    print(f"✅ Gemini Provider 초기화 완료")
                else:
                    print("⚠️ GEMINI_API_KEY 환경변수 필요")
            else:
                print(f"⚠️ 알 수 없는 LLM Provider: {provider_type}")
        
        return self._llm_provider
    
    # ==========================================================================
    # 유틸리티 메서드
    # ==========================================================================
    
    def get_initialization_status(self) -> dict:
        """초기화 상태 반환"""
        return self._initialized.copy()
    
    def reset(self):
        """모든 캐시 초기화"""
        self._sentiment_analyzer = None
        self._keyword_extractor = None
        self._keyword_aggregator = None
        self._weight_calculator = None
        self._llm_provider = None
        
        for key in self._initialized:
            self._initialized[key] = False
        
        print("🔄 Container 캐시 초기화 완료")
    
    def override(self, **kwargs):
        """
        의존성 오버라이드 (테스트용)
        
        Example:
            >>> container.override(
            ...     sentiment_analyzer=MockAnalyzer(),
            ...     llm_provider=MockLLM()
            ... )
        """
        for name, instance in kwargs.items():
            attr_name = f"_{name}"
            if hasattr(self, attr_name):
                setattr(self, attr_name, instance)
                self._initialized[name] = True
                print(f"🔧 {name} 오버라이드 완료")
            else:
                print(f"⚠️ 알 수 없는 의존성: {name}")
    
    def __repr__(self) -> str:
        initialized = [k for k, v in self._initialized.items() if v]
        return f"Container(initialized={initialized})"


# ==============================================================================
# 편의 함수
# ==============================================================================

_default_container: Optional[Container] = None


def get_container(config: PipelineConfigDTO = None) -> Container:
    """
    기본 Container 인스턴스 가져오기 (싱글톤 패턴)
    
    Args:
        config: 새 Container 생성 시 사용할 설정
        
    Returns:
        Container 인스턴스
    """
    global _default_container
    
    if _default_container is None or config is not None:
        _default_container = Container(config)
    
    return _default_container


def reset_container():
    """기본 Container 초기화"""
    global _default_container
    if _default_container:
        _default_container.reset()
    _default_container = None


__all__ = [
    'Container',
    'get_container',
    'reset_container',
]
