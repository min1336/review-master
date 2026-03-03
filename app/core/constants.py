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

# -- 지역 그룹 매핑 (필터용 8대 분류) --
# key: branch_summaries.region.split()[0], value: 필터 표시명
REGION_GROUP_MAP: dict[str, str] = {
    # 표준 시/도 prefix
    "서울": "서울",
    "경기": "경기도",
    "인천": "경기도",
    "강원": "강원도",
    "충남": "충청도",
    "충북": "충청도",
    "대전": "충청도",
    "세종": "충청도",
    "전남": "전라도",
    "전북": "전라도",
    "광주": "전라도",
    "경남": "경상도",
    "경북": "경상도",
    "부산": "경상도",
    "대구": "경상도",
    "울산": "경상도",
    "제주": "제주도",
    "해외": "해외",
    # 공항/도시명 prefix (비표준)
    "김포공항": "서울",
    "강남": "서울",
    "인천공항": "경기도",
    "김포": "경기도",
    "강릉": "강원도",
    "속초": "강원도",
    "여수": "전라도",
    "전주": "전라도",
    "김해공항": "경상도",
    "김해": "경상도",
    "대구공항": "경상도",
    "경주": "경상도",
    "제주공항": "제주도",
}
REGION_GROUP_ORDER: list[str] = [
    "서울", "경기도", "강원도", "충청도", "전라도", "경상도", "제주도", "해외",
]
# 역매핑: 그룹명 → 해당 region prefix 목록 (서버 필터링용)
REGION_GROUP_PREFIXES: dict[str, list[str]] = {}
for _prefix, _group in REGION_GROUP_MAP.items():
    REGION_GROUP_PREFIXES.setdefault(_group, []).append(_prefix)
