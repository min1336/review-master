"""
임베딩 기반 태그 분류기 (v2.0)

BERT 임베딩 + 코사인 유사도로 키워드를 태그 그룹에 분류
+ 규칙 기반 감정 판단 (하이브리드)

주요 기능:
1. 태그 분류
   - 규칙 기반 매핑 (RULE_BASED_TAG_MAPPING) - 우선 적용
   - 임베딩 기반 분류 (코사인 유사도 >= 0.3)

2. 감정 판단
   - NEGATIVE_PATTERNS: 100+개 부정 패턴 (불친절, 비싸, 냄새, 최악, 쩔어 등)
   - POSITIVE_PATTERNS: 긍정 패턴 (친절, 깨끗, 만족 등)
   - POSITIVE_EXCEPTIONS: 오탐 방지 (편안하다, 생각하지 못한 등)
   - DOUBLE_NEGATION_PATTERNS: 이중부정→긍정 (불편없다, 불만없다 등)

3. 문맥 기반 분석
   - 키워드 앞뒤 20자 윈도우에서 감정 패턴 탐지
   - 긍정 키워드 + 부정 표현 → 부정으로 반전 (친절하지 않다)
   - 이중부정 패턴 → 긍정으로 처리 (불편함이 없다)

변경 이력:
- 2026-01-19: v2.0 - 이중부정 처리, 긍정예외 확장, 윈도우 크기 20으로 확대
- 2026-01-19: v1.1 - 규칙 기반 태그 매핑 추가 (브레이크→차량상태)
- 2026-01-16: v1.0 - 초기 구현
"""
import re
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

from .tag_embeddings import TagEmbeddingManager, TAG_DESCRIPTIONS

logger = logging.getLogger(__name__)


# 부정 키워드 패턴 (감정 판단용)
# 주의: 문맥 검색 시 ^앵커 없이 사용됨
NEGATIVE_PATTERNS = [
    # 불- 접두사 (문맥에서도 매칭되도록 앵커 제거)
    r'불친절',    # 불친절
    r'불편',      # 불편
    r'불만',      # 불만족
    r'불쾌',      # 불쾌
    r'불량',      # 불량
    r'불안(?!전)', # 불안 (불안전 제외)
    r'불결',      # 불결
    # 비싸- 관련
    r'비싸',      # 비싸, 비쌈
    r'비싼',      # 비싼
    r'비쌌',      # 비쌌
    r'비싸요',    # 비싸요
    r'비쌉니다',  # 비쌉니다
    # 안- 접두사
    r'안\s*좋',   # 안좋, 안 좋
    r'안되',      # 안됨
    r'안나',      # 안나 (연결 안나)
    # 부정 어근 (구체적으로)
    r'없어[요서]',  # 없어요, 없어서
    r'없었',       # 없었다
    r'없다',       # 없다
    r'없음',       # 없음
    r'없는',       # 없는
    r'없고',       # 없고
    r'늦었',       # 늦었다
    r'늦은',       # 늦은
    r'늦게',       # 늦게
    r'느리',       # 느리다, 느린
    r'더럽',       # 더럽다
    r'더러움',     # 더러움
    r'더러웠',     # 더러웠다
    r'드러웠',     # 드러웠 (구어체)
    r'드러워',     # 드러워 (구어체)
    r'지저분',     # 지저분하다
    r'낡',         # 낡다
    r'오래된',     # 오래된
    r'오래됐',     # 오래됐다
    r'노후',       # 노후
    r'좁은',       # 좁은
    r'좁아',       # 좁아
    r'멀어',       # 멀어
    r'멀었',       # 멀었
    r'나쁘',       # 나쁘다
    r'나빠',       # 나빠 (기분 나빠)
    r'나쁜',       # 나쁜
    r'싫',         # 싫다
    r'실망',       # 실망
    r'후회',       # 후회
    r'최악',       # 최악
    r'별로',       # 별로
    r'아쉬',       # 아쉽다
    r'부족',       # 부족하다
    r'힘들',       # 힘들다
    r'어려',       # 어렵다, 어려웠, 어려운
    r'고장',       # 고장
    r'냄새',       # 냄새
    r'시끄',       # 시끄럽다
    r'답답',       # 답답하다
    r'짜증',       # 짜증
    r'화[가났]',   # 화가, 화났
    r'오래걸',     # 오래걸리다
    r'기다[려렸]', # 기다려, 기다렸
    r'어이없',     # 어이없다
    r'어처구니없', # 어처구니없다
    r'쓸데없',     # 쓸데없다
    # 차량/서비스 관련 부정
    r'담배',       # 담배 (냄새)
    r'쩔어',       # 쩔어 (담배에 쩔어)
    r'심하',       # 심하다, 심하게, 심한
    r'심했',       # 심했다
    r'흠집',       # 흠집
    r'찍힘',       # 찍힘
    r'긁힘',       # 긁힘
    r'파손',       # 파손
    r'오염',       # 오염
    r'먼지',       # 먼지
    r'이물',       # 이물질
    r'악취',       # 악취
    r'퀴퀴',       # 퀴퀴한
    r'꿉꿉',       # 꿉꿉한
    r'눅눅',       # 눅눅한
    r'텁텁',       # 텁텁한
    r'덜덜',       # 덜덜 (차가 덜덜거려)
    r'이상해',     # 이상해 (브레이크 이상해)
    r'이상하',     # 이상하다
    r'이상한',     # 이상한
    # 가격 관련 부정
    r'바가지',     # 바가지
    r'과금',       # 과금
    r'추가요금',   # 추가요금
    r'추가비용',   # 추가비용
    r'손해',       # 손해
    r'호구',       # 호구
    r'호갱',       # 호갱
    r'이해.{0,3}안',   # 이해가 안, 이해안가
    r'납득.{0,3}안',   # 납득이 안
    # 서비스 관련 부정
    r'무시',       # 무시
    r'무성의',     # 무성의
    r'무책임',     # 무책임
    r'퉁명',       # 퉁명스럽다
    r'불성실',     # 불성실
    r'불신',       # 불신
    r'거짓',       # 거짓
    r'사기',       # 사기
    r'먹튀',       # 먹튀
    r'기분.{0,5}안',  # 기분 안좋
    r'기분.{0,5}나빠', # 기분 나빠
    # 부정 표현 (문맥에서 긍정 반전용)
    r'지\s*않',    # ~지 않다, ~지않다
    r'지\s*못',    # ~지 못하다
    r'못\s*하',    # 못 하다, 못하다
    r'(?:^|[^가-힣])안\s*하',  # 안 하다 (편안하, 만안하 제외)
    r'좋지\s*않',  # 좋지 않다
    r'없지\s*않',  # 없지 않다 (이중부정 주의)
    r'도.{0,3}안되',  # ~도 안되고
    r'도.{0,3}없',    # ~도 없고
]

# 긍정/중립 예외 패턴 (부정 패턴에 매칭되지만 실제 부정이 아닌 표현)
POSITIVE_EXCEPTIONS = [
    '틀림없',     # 틀림없이
    '끄떡없',     # 끄떡없다
    '변함없',     # 변함없이
    '다름없',     # 다름없이
    '거침없',     # 거침없이
    '막힘없',     # 막힘없이
    '흠잡을데없',  # 흠잡을데없다
    '나무랄데없',  # 나무랄데없다
    '부족함없',   # 부족함없이
    '손색없',     # 손색없다
    '어김없',     # 어김없이
    '번화가',     # 번화가 (장소)
    '불쾌지수',   # 불쾌지수 (날씨)
    # 오탐 방지 (안\s*하 패턴 예외)
    '편안',       # 편안하다
    '불안전',     # 불안전 (이미 불안에서 제외)
    '만안',       # 만안구 (지명)
    # 긍정적 맥락의 부정 표현
    '생각하지 못한',   # 누구도 생각하지 못한 (기대 이상)
    '생각지 못한',     # 생각지 못한
    '상상하지 못한',   # 상상하지 못한
    '기대하지 못한',   # 기대하지 못한
]

# 이중부정 패턴 (부정어 + 없다/않다/못하다 = 긍정)
DOUBLE_NEGATION_PATTERNS = [
    # ~없다 패턴
    r'불편.{0,5}없',    # 불편함이 없다
    r'불만.{0,15}없',   # 불만이 없다, 불만이라고 할 부분없다
    r'문제.{0,5}없',    # 문제가 없다
    r'걱정.{0,5}없',    # 걱정이 없다
    r'부족.{0,5}없',    # 부족함이 없다
    r'부족함.{0,5}없',  # 부족함 없이
    r'아쉬.{0,5}없',    # 아쉬움이 없다
    r'흠.{0,5}없',      # 흠이 없다
    r'탈.{0,5}없',      # 탈이 없다
    r'냄새.{0,10}없',   # 냄새가 없다
    r'냄새.{0,10}안.{0,3}나',  # 냄새도 안나고
    # "하나도" 패턴
    r'하나도.{0,5}없',  # 하나도 없다
    r'하나도.{0,5}안',  # 하나도 안
    r'전혀.{0,5}없',    # 전혀 없다
    r'전혀.{0,5}안',    # 전혀 안
    r'별로.{0,5}없',    # 별로 없다
    # ~없이 패턴
    r'부족함\s*없이',   # 부족함 없이
    r'불편함\s*없이',   # 불편함 없이
    r'문제\s*없이',     # 문제 없이
    # ~못하다/~지 못하다 패턴
    r'불편.{0,10}못',   # 불편함을 느끼지 못했다
    r'불만.{0,10}못',   # 불만을 느끼지 못했다
    r'문제.{0,10}못',   # 문제를 느끼지 못했다
]

# 명시적 긍정 패턴 (이 패턴에 매칭되어야 긍정으로 분류)
POSITIVE_PATTERNS = [
    # 서비스/응대 긍정
    r'친절',       # 친절하다
    r'상냥',       # 상냥하다
    r'정성',       # 정성스럽다
    r'배려',       # 배려
    r'감사',       # 감사
    r'고마',       # 고맙다
    r'칭찬',       # 칭찬
    r'추천',       # 추천
    r'최고',       # 최고
    r'좋았',       # 좋았다
    r'좋아요',     # 좋아요
    r'좋은',       # 좋은
    r'좋습',       # 좋습니다
    r'훌륭',       # 훌륭하다
    r'완벽',       # 완벽하다
    r'만족',       # 만족
    r'편안',       # 편안하다
    r'편리',       # 편리하다
    r'편해',       # 편해요
    r'편하',       # 편하다
    r'쾌적',       # 쾌적하다
    r'빠른',       # 빠른
    r'빠르',       # 빠르다
    r'신속',       # 신속하다
    # 차량 상태 긍정
    r'깨끗',       # 깨끗하다
    r'청결',       # 청결하다
    r'깔끔',       # 깔끔하다
    r'새차',       # 새차
    r'신차',       # 신차
    r'넓은',       # 넓은
    r'넓어',       # 넓어
    r'쾌적',       # 쾌적
    r'관리',       # 관리 (잘 되어 있는)
    r'정비',       # 정비
    # 가격 긍정
    r'저렴',       # 저렴하다
    r'싸다',       # 싸다
    r'싸요',       # 싸요
    r'싼',         # 싼
    r'합리',       # 합리적
    r'가성비',     # 가성비
    r'착한',       # 착한 (가격)
    r'할인',       # 할인
    r'혜택',       # 혜택
    # 위치 긍정
    r'가까',       # 가깝다
    r'접근',       # 접근성
    r'찾기쉬',     # 찾기쉬운
    # 기타 긍정
    r'감동',       # 감동
    r'인상',       # 인상적
    r'기대',       # 기대 이상
    r'재방문',     # 재방문
    r'재이용',     # 재이용
    r'또.*이용',   # 또 이용
    r'다시.*이용', # 다시 이용
    '화가$',      # 화가 (그림 그리는 사람) - 단독 사용시
]

# 컴파일된 패턴
_NEGATIVE_REGEX = re.compile('|'.join(NEGATIVE_PATTERNS))
_POSITIVE_EXCEPTION_REGEX = re.compile('|'.join(POSITIVE_EXCEPTIONS))
_POSITIVE_REGEX = re.compile('|'.join(POSITIVE_PATTERNS))
_DOUBLE_NEGATION_REGEX = re.compile('|'.join(DOUBLE_NEGATION_PATTERNS))

# 일반 긍정어 (특정 태그에 매핑하지 않음 - 단독 사용 시 '기타' 처리)
GENERAL_POSITIVE_KEYWORDS = {
    '좋', '만족', '굿', 'good', '최고', '훌륭', '완벽', '추천', '강추', '최곱', '짱',
    '좋아', '좋아요', '좋았', '좋은', '좋네', '좋습', '만족해', '만족스러',
    '굿굿', 'good', 'nice', 'great', 'best', '베스트',
}

# 규칙 기반 태그 매핑 (임베딩보다 우선 적용)
# 임베딩이 잘 구분하지 못하는 전문 용어에 사용
# v2.2: 키워드 보강 (배달, 대여, 예약, 오래된, 빵꾸 등)
RULE_BASED_TAG_MAPPING = {
    '보험/보장': [
        '보험', '보장', '면책', '면책금', '자기부담', '자기부담금', '완전자차',
        '자차', '대인', '대물', '대인대물', '보상', '사고', '보험료', '책임',
        '커버', '안심', '슈퍼면책', '사고접수', '사고처리', '손해', '배상',
        '종합보험', '책임보험', '자차보험',
    ],
    '반납/픽업': [
        # 반납/픽업 절차
        '반납', '픽업', '인수', '수령', '전달', '인계', '반환',
        '차량인도', '출차', '입차', '수거', '서류', '계약서',
        # 대여/렌트
        '대여', '렌트', '렌탈', '빌리', '빌렸',
    ],
    '배차/시간': [
        # 배차 관련
        '배차', '차종', '차량변경', '대차', '차종변경', '배정',
        # 배달/딜리버리
        '배달', '딜리버리', '배송', '탁송',
        # 시간 관련
        '지연', '늦게', '늦음', '늦었', '기다림', '기다리', '대기시간',
        '재촉', '독촉', '급하', '빨리빨리', '서두르',
        '약속시간', '예약시간', '출발시간', '도착시간',
        '노쇼', '취소',
    ],
    '서비스': [
        '셔틀', '셔틀버스', '대기실', '휴게실', '주차', '주차장', '와이파이',
        'wifi', '충전', '음료', '커피',
        # 예약/문의
        '예약', '예약확인', '문의', '상담', '전화',
    ],
    '차량외관': [
        # 외부 상태
        '외관', '외부', '외형', '도색', '페인트', '범퍼', '휠', '바퀴',
        '유리', '창문', '와이퍼', '미러', '사이드미러',
        # 외부 손상
        '스크래치', '흠집', '긁힘', '찌그러짐', '파손', '찍힘', '긁힌',
        '움푹', '깨진', '금간',
        # 타이어/주행
        '타이어', '브레이크', '제동', '핸들', '서스펜션',
        # 차량 연식/상태
        '오래된', '낡은', '연식', '노후', '빵꾸', '펑크',
    ],
    '차량청결': [
        # 청결 상태
        '청결', '청소', '깨끗', '지저분', '더럽', '더러', '드러', '드럽',
        '먼지', '때', '얼룩', '오염', '이물질', '쓰레기',
        # 냄새
        '냄새', '담배', '악취', '담배냄새', '곰팡이', '퀴퀴', '쩔어',
        # 실내
        '실내', '내부', '시트', '좌석', '바닥', '매트', '트렁크',
        '에어컨', '히터', '송풍구',
        # 차량 관리
        '세차', '관리', '상태', '컨디션',
    ],
    '고객응대': [
        '친절', '불친절', '응대', '설명', '안내', '직원', '사장', '사장님',
        '태도', '말투', '최악', '짜증', '화나', '어이없',
    ],
    '가성비': [
        '가격', '비싸', '비싼', '저렴', '싼', '합리', '가성비', '호구', '호갱',
        '바가지', '할인', '혜택',
        # 비용/추가금
        '돈', '비용', '추가비용', '추가금', '부담금', '수리비',
    ],
}


class EmbeddingTagClassifier:
    """
    임베딩 기반 태그 자동 분류기

    동작 원리:
    1. 각 태그 그룹의 대표 임베딩 계산 (초기화 시)
    2. 입력 키워드의 임베딩 계산
    3. 코사인 유사도로 가장 가까운 태그 그룹 선택
    """

    # 권장 모델: 한국어 지원 다국어 모델
    DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

    # 유사도 임계값
    DEFAULT_THRESHOLD = 0.3

    def __init__(
        self,
        model_name: Optional[str] = None,
        similarity_threshold: float = DEFAULT_THRESHOLD,
        cache_path: Optional[str] = None,
        lazy_load: bool = True
    ):
        """
        Args:
            model_name: Sentence Transformer 모델명
            similarity_threshold: 최소 유사도 임계값 (미만이면 '기타')
            cache_path: 태그 임베딩 캐시 파일 경로
            lazy_load: True면 첫 사용 시 모델 로딩
        """
        self.model_name = model_name or self.DEFAULT_MODEL
        self.similarity_threshold = similarity_threshold
        self.cache_path = cache_path

        self._model = None
        self._tag_manager: Optional[TagEmbeddingManager] = None
        self._tag_embeddings: Optional[Dict[str, np.ndarray]] = None
        self._tag_names: Optional[List[str]] = None
        self._initialized = False

        if not lazy_load:
            self.initialize()

    def initialize(self) -> bool:
        """
        모델 및 태그 임베딩 초기화

        Returns:
            초기화 성공 여부
        """
        if self._initialized:
            return True

        try:
            logger.info(f"임베딩 모델 로딩 중: {self.model_name}")

            # SentenceTransformer 모델 로딩
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)

            # 태그 임베딩 매니저 초기화
            self._tag_manager = TagEmbeddingManager(
                model=self._model,
                cache_path=self.cache_path
            )

            # 태그 임베딩 로드 또는 계산
            self._tag_embeddings = self._tag_manager.get_or_compute()
            self._tag_names = list(self._tag_embeddings.keys())

            self._initialized = True
            logger.info("EmbeddingTagClassifier 초기화 완료")
            return True

        except ImportError as e:
            logger.error(f"sentence-transformers 패키지가 필요합니다: {e}")
            logger.error("pip install sentence-transformers 실행 필요")
            return False

        except Exception as e:
            logger.error(f"초기화 실패: {e}")
            return False

    def _ensure_initialized(self):
        """초기화 확인 (지연 로딩)"""
        if not self._initialized:
            if not self.initialize():
                raise RuntimeError("EmbeddingTagClassifier 초기화 실패")

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """코사인 유사도 계산"""
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot_product / (norm1 * norm2))

    def _detect_sentiment(self, keyword: str) -> str:
        """
        키워드의 감정 판단 (규칙 기반)

        Args:
            keyword: 판단할 키워드

        Returns:
            'positive', 'negative', 또는 'neutral'
        """
        if not keyword:
            return 'neutral'

        # 긍정 예외 패턴 먼저 확인 (틀림없이, 변함없이 등)
        if _POSITIVE_EXCEPTION_REGEX.search(keyword):
            return 'positive'

        # 부정 패턴 매칭
        if _NEGATIVE_REGEX.search(keyword):
            return 'negative'

        # 긍정 패턴 매칭
        if _POSITIVE_REGEX.search(keyword):
            return 'positive'

        # 어떤 패턴에도 매칭되지 않으면 중립
        return 'neutral'

    def _detect_sentiment_with_context(self, keyword: str, context: str, window_size: int = 20) -> str:
        """
        문맥을 고려한 키워드 감정 판단

        중립 키워드의 경우 주변 단어를 확인하여 감성 결정.
        예: "가격이 저렴해요" → 가격(중립) + 저렴(긍정) → 긍정

        Args:
            keyword: 판단할 키워드
            context: 키워드가 포함된 원문 텍스트
            window_size: 키워드 주변 탐색할 글자 수

        Returns:
            'positive', 'negative', 또는 'neutral'
        """
        # 먼저 키워드 자체 감성 확인
        base_sentiment = self._detect_sentiment(keyword)

        # 문맥이 없으면 기본 감성 반환
        if not context or keyword not in context:
            return base_sentiment

        # 키워드 위치 찾기
        pos = context.find(keyword)
        if pos == -1:
            return base_sentiment

        # 윈도우 범위 추출 (키워드 앞뒤 window_size 글자)
        start = max(0, pos - window_size)
        end = min(len(context), pos + len(keyword) + window_size)
        window = context[start:end]

        # 1. 이중부정 패턴 확인 (부정어 + 없다 = 긍정)
        # 예: "불편함이 없었습니다" → 긍정
        if _DOUBLE_NEGATION_REGEX.search(window):
            return 'positive'

        # 2. 긍정 예외 패턴 확인 (오탐 방지)
        # 예: "편안하게" → 편안 예외이므로 negation 패턴 무시
        # 예: "생각하지 못한 세심한" → 긍정 맥락이므로 부정 패턴 무시
        has_positive_exception = _POSITIVE_EXCEPTION_REGEX.search(window)
        if has_positive_exception:
            if base_sentiment == 'positive':
                return 'positive'
            # 긍정 예외가 있으면 중립 키워드도 긍정으로 처리
            if base_sentiment == 'neutral':
                return 'positive'

        # 3. 부정 표현 패턴 ("~지 않다", "~하지 않다", "안 좋다" 등)
        negation_pattern = re.compile(r'지\s*않|지\s*못|못\s*하|(?<![가-힣])안\s*하|안\s*좋|너무\s*안')

        # 긍정 키워드 + 부정 표현 → 부정으로 반전
        # 예: "친절하지 않다" → 친절(긍정) + "지 않" → 부정
        # 단, 긍정 예외 패턴이 있으면 반전하지 않음
        if base_sentiment == 'positive' and negation_pattern.search(window):
            if not has_positive_exception:
                return 'negative'

        # 이미 긍정/부정이면 그대로 반환
        if base_sentiment != 'neutral':
            return base_sentiment

        # 윈도우에서 부정 패턴 먼저 확인 (부정이 더 중요)
        if _NEGATIVE_REGEX.search(window):
            return 'negative'

        # 윈도우에서 긍정 패턴 확인
        if _POSITIVE_REGEX.search(window):
            return 'positive'

        # 여전히 판단 불가면 중립
        return 'neutral'

    def _check_rule_based_mapping(self, keyword: str) -> Optional[Tuple[str, float]]:
        """
        규칙 기반 태그 매핑 확인 (임베딩보다 우선)

        Args:
            keyword: 확인할 키워드

        Returns:
            (태그명, 1.0) 또는 None (규칙에 없으면)
        """
        keyword_lower = keyword.lower().strip()
        for tag, keywords in RULE_BASED_TAG_MAPPING.items():
            for rule_kw in keywords:
                # 정확히 일치하거나 포함 관계 확인
                if keyword_lower == rule_kw or rule_kw in keyword_lower:
                    return (tag, 1.0)
        return None

    def classify(self, keyword: str) -> Tuple[str, float]:
        """
        키워드를 태그 그룹으로 분류

        Args:
            keyword: 분류할 키워드

        Returns:
            (태그_그룹명, 유사도_점수)
            유사도가 임계값 미만이면 ('기타', 유사도)
        """
        self._ensure_initialized()

        if not keyword or not keyword.strip():
            return ('기타', 0.0)

        keyword_lower = keyword.lower().strip()

        # 0. 일반 긍정어는 특정 태그에 매핑하지 않음 (단독 사용 시 '기타')
        if keyword_lower in GENERAL_POSITIVE_KEYWORDS:
            return ('기타', 0.0)

        # 1. 규칙 기반 매핑 먼저 확인
        rule_result = self._check_rule_based_mapping(keyword)
        if rule_result:
            return rule_result

        # 2. 임베딩 기반 분류
        # 키워드 임베딩 계산
        keyword_embedding = self._model.encode(keyword, convert_to_numpy=True)

        # 각 태그 그룹과의 유사도 계산
        similarities = {}
        for tag_name, tag_embedding in self._tag_embeddings.items():
            sim = self._cosine_similarity(keyword_embedding, tag_embedding)
            similarities[tag_name] = sim

        # 가장 높은 유사도 태그 선택
        best_tag = max(similarities, key=similarities.get)
        best_score = similarities[best_tag]

        # 임계값 확인
        if best_score < self.similarity_threshold:
            return ('기타', best_score)

        return (best_tag, best_score)

    def classify_batch(
        self,
        keywords: List[str],
        return_all_scores: bool = False
    ) -> List[Tuple[str, float]]:
        """
        배치 분류 (성능 최적화)

        Args:
            keywords: 키워드 리스트
            return_all_scores: True면 모든 태그 점수 반환

        Returns:
            [(태그_그룹명, 유사도_점수), ...] 리스트
        """
        self._ensure_initialized()

        if not keywords:
            return []

        # 결과 배열 초기화
        results = [('기타', 0.0) for _ in keywords]

        # 규칙 기반 매핑 먼저 처리
        embedding_indices = []  # 임베딩 분류가 필요한 인덱스
        embedding_keywords = []

        for i, kw in enumerate(keywords):
            if not kw or not kw.strip():
                continue

            kw_lower = kw.lower().strip()

            # 일반 긍정어는 '기타'로 처리
            if kw_lower in GENERAL_POSITIVE_KEYWORDS:
                results[i] = ('기타', 0.0)
                continue

            rule_result = self._check_rule_based_mapping(kw)
            if rule_result:
                results[i] = rule_result
            else:
                embedding_indices.append(i)
                embedding_keywords.append(kw)

        # 임베딩 분류가 필요한 키워드가 없으면 바로 반환
        if not embedding_keywords:
            return results

        # 배치 인코딩 (훨씬 빠름)
        keyword_embeddings = self._model.encode(
            embedding_keywords,
            convert_to_numpy=True,
            show_progress_bar=False
        )

        # 태그 임베딩 행렬 구성
        tag_matrix = np.array([
            self._tag_embeddings[tag] for tag in self._tag_names
        ])

        # 코사인 유사도 행렬 계산 (배치)
        # keyword_embeddings: (N, D), tag_matrix: (T, D)
        # 정규화
        kw_norms = np.linalg.norm(keyword_embeddings, axis=1, keepdims=True)
        tag_norms = np.linalg.norm(tag_matrix, axis=1, keepdims=True)

        kw_normalized = keyword_embeddings / (kw_norms + 1e-9)
        tag_normalized = tag_matrix / (tag_norms + 1e-9)

        # 유사도 행렬: (N, T)
        similarity_matrix = np.dot(kw_normalized, tag_normalized.T)

        # 결과 구성
        for idx, orig_idx in enumerate(embedding_indices):
            scores = similarity_matrix[idx]
            best_idx = np.argmax(scores)
            best_score = float(scores[best_idx])
            best_tag = self._tag_names[best_idx]

            if best_score < self.similarity_threshold:
                results[orig_idx] = ('기타', best_score)
            else:
                results[orig_idx] = (best_tag, best_score)

        return results

    def classify_with_all_scores(
        self,
        keyword: str
    ) -> Dict[str, float]:
        """
        모든 태그 그룹에 대한 유사도 점수 반환

        Args:
            keyword: 분류할 키워드

        Returns:
            {태그명: 유사도} 딕셔너리
        """
        self._ensure_initialized()

        if not keyword or not keyword.strip():
            return {tag: 0.0 for tag in self._tag_names}

        keyword_embedding = self._model.encode(keyword, convert_to_numpy=True)

        scores = {}
        for tag_name, tag_embedding in self._tag_embeddings.items():
            scores[tag_name] = self._cosine_similarity(
                keyword_embedding, tag_embedding
            )

        return scores

    def get_tag_color(self, tag_name: str) -> str:
        """태그 색상 반환"""
        if self._tag_manager:
            return self._tag_manager.get_tag_color(tag_name)
        return '#6b7280'

    def get_tag_names(self) -> List[str]:
        """태그 그룹명 목록 반환"""
        self._ensure_initialized()
        return self._tag_names.copy()

    @property
    def is_initialized(self) -> bool:
        """초기화 여부"""
        return self._initialized

    # ========== 감정 포함 분류 메서드 ==========

    def classify_with_sentiment(
        self,
        keyword: str,
        context: str = None
    ) -> Tuple[str, float, str]:
        """
        키워드를 태그 그룹으로 분류 + 감정 판단

        Args:
            keyword: 분류할 키워드
            context: 키워드가 포함된 원문 텍스트 (부정 표현 감지용)

        Returns:
            (태그_그룹명, 유사도_점수, 감정)
            감정: 'positive', 'negative', 또는 'neutral'
        """
        tag, score = self.classify(keyword)
        # 문맥이 있으면 문맥 기반 감정 판단, 없으면 키워드만으로 판단
        if context:
            sentiment = self._detect_sentiment_with_context(keyword, context)
        else:
            sentiment = self._detect_sentiment(keyword)
        return (tag, score, sentiment)

    def classify_batch_with_sentiment(
        self,
        keywords: List[str]
    ) -> List[Tuple[str, float, str]]:
        """
        배치 분류 + 감정 판단

        Args:
            keywords: 키워드 리스트

        Returns:
            [(태그_그룹명, 유사도_점수, 감정), ...] 리스트
        """
        # 태그 분류
        classifications = self.classify_batch(keywords)

        # 감정 판단 추가
        results = []
        for (tag, score), keyword in zip(classifications, keywords):
            sentiment = self._detect_sentiment(keyword)
            results.append((tag, score, sentiment))

        return results

    def classify_with_context(
        self,
        keyword: str,
        context: str
    ) -> Tuple[str, float, str]:
        """
        문맥을 고려한 키워드 분류 + 감정 판단

        Args:
            keyword: 분류할 키워드
            context: 키워드가 포함된 원문 텍스트

        Returns:
            (태그_그룹명, 유사도_점수, 감정)
        """
        tag, score = self.classify(keyword)
        sentiment = self._detect_sentiment_with_context(keyword, context)
        return (tag, score, sentiment)

    def classify_keywords_from_review(
        self,
        keywords: List[str],
        review_text: str
    ) -> List[Tuple[str, float, str]]:
        """
        리뷰 텍스트에서 추출된 키워드들을 문맥 기반으로 분류

        Args:
            keywords: 리뷰에서 추출된 키워드 리스트
            review_text: 원본 리뷰 텍스트

        Returns:
            [(태그_그룹명, 유사도_점수, 감정), ...] 리스트
        """
        self._ensure_initialized()

        if not keywords:
            return []

        # 태그 분류 (배치)
        classifications = self.classify_batch(keywords)

        # 문맥 기반 감정 판단
        results = []
        for (tag, score), keyword in zip(classifications, keywords):
            sentiment = self._detect_sentiment_with_context(keyword, review_text)
            results.append((tag, score, sentiment))

        return results
