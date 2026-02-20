"""
프로젝트 전역 상수

분석, 리포트, 캐시, 감쇠 등에서 사용하는 임계값과 설정값을
한 곳에서 관리합니다.
"""

# -- 임베딩 / 분류 --
EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
SIMILARITY_THRESHOLD = 0.35
CONTEXT_WINDOW_SIZE = 30

# -- 리포트 임계값 --
STRENGTH_POSITIVE_RATIO = 60     # 카테고리 긍정률 >= 60% -> 현상유지
IMPROVEMENT_NEGATIVE_RATIO = 20  # 카테고리 부정률 >= 20% -> 보완필요

# -- 캐시 무효화 --
REVIEW_CHANGE_THRESHOLD = 30
CACHE_MIN_NEW_REVIEWS = 5
CACHE_TAG_COUNT_RATIO = 0.15
CACHE_SENTIMENT_DRIFT = 8.0

# -- 시간 감쇠 --
DECAY_LAMBDA = 0.01              # 반감기 ~69일
