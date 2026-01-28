# Review Summary AI

Carmore 렌트카 리뷰 요약 시스템 - 운영팀 모니터링 대시보드

## Tech Stack

- **Backend**: Python 3.x, FastAPI
- **NLP**: MeCab (한국어 형태소 분석), Sentence-Transformers
- **LLM**: OpenAI GPT-4o-mini
- **Database**: Supabase (PostgreSQL)
- **Data**: pandas, openpyxl

## Key Constants

```python
MIN_REVIEWS_PER_BRANCH = 30      # 최소 리뷰 수
MIN_REVIEW_LENGTH = 5            # 최소 리뷰 길이
OPENAI_RPM = 3500                # API Rate Limit
MAX_REVIEWS_PER_BRANCH = 30      # recent_reviews 저장 개수
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
SIMILARITY_THRESHOLD = 0.3       # 태그 분류 최소 유사도
```

## Directory Structure

```
app/
├── main.py                        # FastAPI 진입점
│
├── api/v1/                        # API 레이어
│   ├── api.py                     # 라우터 등록
│   └── endpoints/
│       ├── deps.py                # 의존성 주입 (DI)
│       ├── pages.py               # HTML 페이지 렌더링
│       ├── sentiment.py           # 감정 API
│       ├── summaries.py           # 요약 API (/api/v2/*)
│       └── tags.py                # 태그 API (/api/tags/*)
│
├── domain/                        # 도메인 로직 (핵심 비즈니스)
│   ├── analysis/                  # 분석 모듈
│   │   ├── extractor.py           # MeCab 키워드 추출
│   │   ├── absa.py                # 규칙 기반 ABSA
│   │   ├── chunker.py             # 절 단위 청킹
│   │   ├── aggregator.py          # 키워드 집계
│   │   ├── weight.py              # 가중치 계산
│   │   ├── mapper.py              # 태그 매핑
│   │   ├── patterns.py            # 감정 패턴
│   │   ├── embedding_classifier.py
│   │   ├── hybrid_classifier.py
│   │   └── tag_embeddings.py
│   └── pipeline/                  # 파이프라인
│       ├── batch_pipeline.py      # Excel 전체 처리
│       └── incremental_pipeline.py # API 증분 처리
│
├── infrastructure/                # 외부 시스템 연동
│   └── llm/                       # LLM 프로바이더
│       ├── base.py                # 추상 클래스
│       ├── openai_provider.py     # OpenAI 구현
│       ├── prompts.py             # 프롬프트 템플릿
│       ├── rate_limiter.py        # Rate Limiting
│       └── validator.py           # 응답 검증
│
├── services/                      # 서비스 레이어 (API 비즈니스 로직)
│   ├── summary_service.py         # 요약 CRUD + 상세분석
│   ├── tag_service.py             # 태그/카테고리/매핑
│   ├── sentiment_service.py       # 감정 통계
│   └── carmore_service.py         # Carmore API 연동
│
├── crud/                          # Repository 레이어 (DB 접근)
│   ├── session.py                 # Supabase 클라이언트
│   ├── unit_of_work.py            # UoW 패턴
│   ├── base.py                    # BaseRepository
│   ├── summary_crud.py
│   ├── tag_crud.py
│   ├── branch_tag_crud.py
│   ├── review_crud.py
│   ├── sentiment_crud.py
│   └── affiliate_crud.py
│
├── models/                        # DB 모델 (Pydantic)
│   ├── summary.py
│   ├── tag.py
│   ├── review.py
│   ├── sentiment.py
│   └── affiliate.py
│
├── schemas/                       # API 스키마 (DTO)
│   ├── summary.py                 # 요약 요청/응답
│   ├── tag.py                     # 태그 요청/응답
│   ├── entities.py                # DB 엔티티
│   ├── dto.py                     # 파이프라인 DTO
│   └── common.py                  # 공통 스키마
│
├── core/                          # 설정
│   ├── config.py                  # 환경변수 설정
│   └── stopwords.py               # 불용어 사전
│
└── templates/                     # HTML 템플릿
    ├── dashboard_v2.html          # 메인 대시보드
    └── tag_tester.html            # 태그 테스트 페이지
```

## Common Commands

```bash
# 앱 실행
cd app && python main.py

# 또는 uvicorn 직접 실행
cd app && uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## API Endpoints

### 요약 API (`/api/v2/`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/summaries` | 요약 목록 |
| GET | `/summaries/{id}` | 요약 상세 |
| GET | `/summaries/{id}/detail` | 지점 상세 분석 (JSON) |
| PUT | `/summaries/{id}` | 요약 수정 |
| PUT | `/summaries/{id}/status` | 상태 변경 |
| POST | `/summaries/{id}/regenerate` | AI 재생성 |
| GET | `/stats` | 통계 |

### 태그 API (`/api/tags/`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/list` | 태그 목록 |
| GET | `/groups` | 태그 그룹 |
| GET | `/{id}` | 태그 상세 |
| POST | `/` | 태그 생성 |
| GET | `/batch` | 일괄 조회 |
| GET | `/branch/{id}` | 지점별 태그 |

### 감정 API (`/api/sentiment/`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/stats` | 감정 통계 |
| GET | `/reviews/recent` | 최근 리뷰 |

## Environment Variables

`.env` 파일 필수:
```
OPENAI_API_KEY=sk-...
LLM_PROVIDER=openai
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...
```

## Status Workflow

| DB 값 | 표시 라벨 |
|-------|----------|
| draft | 보류 |
| approved | 승인 |
| published | 게시 |

## 태그 시스템

### 기본 태그 7개
친절도, 사고, 주유, 가격, 청결, 차량상태, 딜리버리

### 감정 판단 방식
- 키워드별 규칙 패턴 매칭 + 문맥 분석
- 부정 패턴: `불친절`, `비싸`, `냄새`, `아쉬운` 등 (100+개)
- 이중부정 처리: `불편함이 없다` → 긍정
- 문맥 윈도우: 키워드 앞뒤 20자

## Architecture Layers

```
Request → API (endpoints) → Service → Domain/CRUD → Response
                              ↓
                         Infrastructure (LLM)
```

| Layer | 역할 |
|-------|------|
| `api/` | HTTP 요청/응답 처리 |
| `services/` | API 비즈니스 로직 |
| `domain/` | 핵심 도메인 로직 (분석, 파이프라인) |
| `infrastructure/` | 외부 시스템 (LLM) |
| `crud/` | DB 접근 |
| `models/` | DB 테이블 매핑 |
| `schemas/` | API 요청/응답 DTO |

## Code Principles

1. **단일 책임**: 하나의 파일/함수는 하나의 역할
2. **의존성 주입**: `deps.py`에서 서비스 생성
3. **UoW 패턴**: `UnitOfWork`로 Repository 묶음 관리
4. **순환 참조 방지**: 함수 내부 import 사용
