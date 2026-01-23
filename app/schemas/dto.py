"""
DTO (Data Transfer Object) 모듈

데이터 전송을 위한 타입 안전한 데이터 클래스들을 정의합니다.
레고 블록처럼 조합하여 사용할 수 있습니다.

구현 일지:
- 2026-01-16: 초기 DTO 클래스 생성 (ReviewDTO, SentimentDTO, SummaryRequestDTO, 
              SummaryResponseDTO, PipelineConfigDTO, PipelineResultDTO)
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime


# ==============================================================================
# Review 관련 DTO
# ==============================================================================

@dataclass
class ReviewDTO:
    """
    리뷰 원본 데이터 전송 객체
    
    엑셀에서 로드한 리뷰 데이터를 타입 안전하게 전달합니다.
    
    Example:
        >>> review = ReviewDTO(
        ...     id=1, 
        ...     branch_id=101, 
        ...     content="서비스가 정말 좋았습니다!"
        ... )
        >>> print(review.content)
        서비스가 정말 좋았습니다!
    """
    id: int
    branch_id: int
    content: str
    branch_name: str = ""
    rating: Optional[float] = None
    created_at: Optional[datetime] = None
    like_count: int = 0
    is_blind: bool = False
    
    def is_valid(self) -> bool:
        """리뷰가 유효한지 검사"""
        return (
            self.content is not None and 
            len(self.content.strip()) >= 5 and 
            not self.is_blind
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            'id': self.id,
            'branch_id': self.branch_id,
            'branch_name': self.branch_name,
            'content': self.content,
            'rating': self.rating,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'like_count': self.like_count,
            'is_blind': self.is_blind
        }


# ==============================================================================
# Sentiment (감정분석) 관련 DTO
# ==============================================================================

@dataclass
class SentimentDTO:
    """
    감정 분석 결과 DTO
    
    기존 SentimentResult와 호환되면서 추가 메타데이터를 포함합니다.
    
    Attributes:
        sentiment: 감정 분류 ('positive', 'neutral', 'negative')
        score: 감정 점수 (0.0 ~ 1.0)
        method: 분석 방법 ('lexicon', 'bert', 'hybrid')
        confidence: 신뢰도 (선택)
    """
    sentiment: Literal['positive', 'neutral', 'negative']
    score: float  # 0.0 ~ 1.0
    method: str   # 'lexicon', 'bert', 'hybrid'
    confidence: Optional[float] = None
    
    @property
    def is_positive(self) -> bool:
        return self.sentiment == 'positive' or self.score >= 0.45
    
    @property
    def is_confident(self) -> bool:
        """신뢰도 높은 결과인지"""
        return self.score >= 0.7 or self.score <= 0.3
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'sentiment': self.sentiment,
            'score': self.score,
            'method': self.method,
            'confidence': self.confidence
        }


# ==============================================================================
# Summary (요약) 관련 DTO
# ==============================================================================

@dataclass
class SummaryRequestDTO:
    """
    LLM 요약 요청 DTO
    
    LLM에 요약 생성을 요청할 때 필요한 모든 정보를 담습니다.
    
    Example:
        >>> request = SummaryRequestDTO(
        ...     branch_id=101,
        ...     branch_name="강남점",
        ...     keywords=["친절", "서비스", "깨끗"],
        ...     representative_reviews=["정말 좋았어요", "추천합니다"],
        ...     review_count=150
        ... )
    """
    branch_id: int
    branch_name: str
    keywords: List[str]
    representative_reviews: List[str]
    review_count: int
    avg_sentiment_score: float = 0.0
    positive_count: int = 0
    negative_count: int = 0
    
    def to_prompt_context(self) -> str:
        """프롬프트용 컨텍스트 문자열 생성"""
        keywords_str = ", ".join(self.keywords[:10])
        reviews_str = "\n".join(f"- {r}" for r in self.representative_reviews[:5])
        
        return f"""
지점: {self.branch_name}
리뷰 수: {self.review_count}개
평균 감정점수: {self.avg_sentiment_score:.2f}
주요 키워드: {keywords_str}

대표 리뷰:
{reviews_str}
"""


@dataclass
class SummaryResponseDTO:
    """
    LLM 요약 응답 DTO
    
    생성된 요약과 메타데이터를 담습니다.
    """
    branch_id: int
    summary: str
    model: str
    tokens_used: int = 0
    is_valid: bool = True
    validation_errors: List[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'branch_id': self.branch_id,
            'summary': self.summary,
            'model': self.model,
            'tokens_used': self.tokens_used,
            'is_valid': self.is_valid,
            'validation_errors': self.validation_errors,
            'generated_at': self.generated_at.isoformat()
        }


# ==============================================================================
# Pipeline 설정 및 결과 DTO
# ==============================================================================

@dataclass
class PipelineConfigDTO:
    """
    파이프라인 설정 DTO
    
    파이프라인 실행에 필요한 모든 설정을 담습니다.
    기본값이 모두 설정되어 있어 그대로 사용 가능합니다.
    
    Example:
        >>> config = PipelineConfigDTO()  # 기본값 사용
        >>> config = PipelineConfigDTO(min_reviews=50)  # 커스텀
    """
    # 필터링 설정
    min_reviews: int = 30          # 지점당 최소 리뷰 수
    min_review_length: int = 5     # 최소 리뷰 글자 수
    
    # 감정분석 설정
    sentiment_threshold: float = 0.45  # 긍정 판정 기준
    confident_high: float = 0.7        # 확실한 긍정
    confident_low: float = 0.3         # 확실한 부정
    use_bert: bool = True              # BERT 사용 여부
    
    # 키워드 설정
    top_n_keywords: int = 10           # 상위 N개 키워드
    use_keyword_weights: bool = True   # 가중치 사용 여부
    
    # 병렬 처리 설정
    use_parallel: bool = True
    n_jobs: int = -1                   # -1 = 모든 CPU 사용
    
    # LLM 설정
    llm_provider: str = "gemini"       # "openai" or "gemini"
    max_tokens: int = 300
    temperature: float = 0.7
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'min_reviews': self.min_reviews,
            'min_review_length': self.min_review_length,
            'sentiment_threshold': self.sentiment_threshold,
            'confident_high': self.confident_high,
            'confident_low': self.confident_low,
            'use_bert': self.use_bert,
            'top_n_keywords': self.top_n_keywords,
            'use_keyword_weights': self.use_keyword_weights,
            'use_parallel': self.use_parallel,
            'n_jobs': self.n_jobs,
            'llm_provider': self.llm_provider,
            'max_tokens': self.max_tokens,
            'temperature': self.temperature
        }


@dataclass
class PipelineStepResultDTO:
    """
    파이프라인 단일 스텝 결과 DTO
    """
    step_name: str
    success: bool
    input_count: int
    output_count: int
    duration_seconds: float = 0.0
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'step_name': self.step_name,
            'success': self.success,
            'input_count': self.input_count,
            'output_count': self.output_count,
            'duration_seconds': self.duration_seconds,
            'error_message': self.error_message
        }


@dataclass
class PipelineResultDTO:
    """
    파이프라인 전체 실행 결과 DTO
    
    모든 스텝의 결과와 통계를 담습니다.
    """
    success: bool
    total_reviews: int
    processed_reviews: int
    total_branches: int
    summaries_generated: int
    steps: List[PipelineStepResultDTO] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    error_message: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    
    def add_step(self, step: PipelineStepResultDTO):
        """스텝 결과 추가"""
        self.steps.append(step)
    
    @property
    def failed_steps(self) -> List[str]:
        """실패한 스텝 이름 목록"""
        return [s.step_name for s in self.steps if not s.success]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'total_reviews': self.total_reviews,
            'processed_reviews': self.processed_reviews,
            'total_branches': self.total_branches,
            'summaries_generated': self.summaries_generated,
            'steps': [s.to_dict() for s in self.steps],
            'total_duration_seconds': self.total_duration_seconds,
            'error_message': self.error_message,
            'started_at': self.started_at.isoformat(),
            'finished_at': self.finished_at.isoformat() if self.finished_at else None
        }


# ==============================================================================
# 내보내기
# ==============================================================================

__all__ = [
    'ReviewDTO',
    'SentimentDTO',
    'SummaryRequestDTO',
    'SummaryResponseDTO',
    'PipelineConfigDTO',
    'PipelineStepResultDTO',
    'PipelineResultDTO',
]
