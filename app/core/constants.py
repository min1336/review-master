"""
프로젝트 전역 상수

분석, 리포트, 캐시, 감쇠 등에서 사용하는 임계값과 설정값을
한 곳에서 관리합니다.
"""

import os

# -- 파이프라인 모드 --
# LIGHTWEIGHT_MODE=true → 임베딩 모델 비활성화 (메모리 ~360MB, 512MB 컨테이너용)
# LIGHTWEIGHT_MODE=false (기본) → 전체 모델 로드 (메모리 ~1GB, 2GB+ 컨테이너용)
LIGHTWEIGHT_MODE = os.getenv("LIGHTWEIGHT_MODE", "false").lower() in ("true", "1", "yes")

# -- 임베딩 / 분류 --
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
SIMILARITY_THRESHOLD = 0.35
CONTEXT_WINDOW_SIZE = 50

# -- 평점 임계값 --
NEGATIVE_RATING_THRESHOLD = 3.0   # 미만(exclusive)이면 부정 판정
HIGH_RATING_THRESHOLD = 4.0       # 이상이면 긍정 판정

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
