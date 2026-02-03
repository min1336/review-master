# Review Summary AI

Carmore 렌트카 리뷰 요약 시스템 - 운영팀 모니터링 대시보드

## Tech Stack

- **Backend**: Python 3.12, FastAPI
- **NLP**: Kiwi (한국어 형태소 분석), FastEmbed (ONNX 기반)
- **LLM**: OpenAI GPT-4o-mini
- **Database**: Supabase (PostgreSQL)
- **Data**: pandas, openpyxl

## Key Constants

```python
OPENAI_RPM = 3500                # API Rate Limit
MAX_REVIEWS_PER_BRANCH = 30      # recent_reviews 저장 개수
EMBEDDING_MODEL = "intfloat/multilingual-e5-small"
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
│       ├── analysis.py            # 분석 페이지 API (/api/analysis/*)
│       ├── sentiment.py           # 감정 API (/api/sentiment/*)
│       ├── summaries.py           # 요약 API (/api/v2/*)
│       └── tags.py                # 태그 API (/api/tags/*)
│
├── domain/                        # 도메인 로직 (핵심 비즈니스)
│   ├── analysis/                  # 분석 모듈
│   │   ├── extractor.py           # Kiwi 키워드 추출
│   │   ├── absa.py                # 규칙 기반 ABSA
│   │   ├── chunker.py             # 절 단위 청킹
│   │   ├── aggregator.py          # 키워드 집계
│   │   ├── patterns.py            # 감정 패턴
│   │   ├── hybrid_classifier.py   # 하이브리드 분류기
│   │   └── tag_embeddings.py      # 태그 임베딩
│   └── pipeline/                  # 파이프라인
│       └── pipeline.py            # 배치/증분 처리
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
│   ├── analysis_service.py        # 분석 페이지 로직
│   ├── summary_service.py         # 요약 CRUD + 상세분석
│   ├── tag_service.py             # 태그/카테고리/매핑
│   ├── sentiment_service.py       # 감정 통계
│   ├── report_service.py          # AI 리포트 생성
│   ├── report_job_service.py      # 비동기 리포트 작업 관리
│   └── carmore_service.py         # Carmore API 연동
│
├── repository/                    # Repository 레이어 (DB 접근)
│   ├── session.py                 # Supabase 클라이언트
│   ├── base.py                    # BaseRepository
│   ├── summary_repository.py      # 요약 Repository
│   ├── tag_repository.py          # 태그 Repository
│   ├── branch_tag_repository.py   # 지점 태그 Repository
│   ├── review_repository.py       # 리뷰 Repository
│   ├── sentiment_repository.py    # 감정 Repository
│   ├── affiliate_repository.py    # 업체 Repository
│   ├── report_repository.py       # 리포트 Repository
│   └── report_job_repository.py   # 비동기 작업 Repository
│
├── models/                        # DB 모델 (Pydantic)
│   ├── summary.py
│   ├── tag.py
│   ├── review.py
│   ├── sentiment.py
│   └── affiliate.py
│
├── schemas/                       # API 스키마 (DTO)
│   ├── dto.py                     # 데이터 전송 객체
│   ├── summary.py                 # 요약 요청/응답
│   ├── tag.py                     # 태그 요청/응답
│   ├── entities.py                # DB 엔티티
│   └── common.py                  # 공통 스키마
│
├── core/                          # 설정
│   ├── config.py                  # 환경변수 설정
│   └── stopwords.py               # 불용어 사전
│
├── scripts/                       # 유틸리티 스크립트
│   └── migrate_sentiments.py      # 마이그레이션
│
└── templates/                     # HTML 템플릿
    ├── dashboard_v2.html          # 메인 대시보드
    ├── analysis.html              # 리뷰 분석 페이지
    └── tag_tester.html            # 태그 테스트 페이지
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
| GET | `/stats/all` | 전체 지점 감정 통계 |
| GET | `/reviews/recent` | 최근 리뷰 |
| POST | `/reviews/cleanup` | 리뷰 정리 |

### 분석 API (`/api/analysis/`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/filters` | 필터 옵션 (지역/업체/지점) |
| GET | `/reviews` | 필터링된 리뷰 목록 |

### 리포트 API (`/api/v2/report/`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/{branch_id}` | 저장된 리포트 조회 (없으면 생성) |
| GET | `/{branch_id}/list` | 리포트 목록 |
| POST | `/{branch_id}/generate` | 동기 리포트 생성 |
| POST | `/{branch_id}/generate/async` | **비동기** 리포트 생성 (job_id 반환) |
| GET | `/{branch_id}/job/{job_id}` | 작업 상태 폴링 (progress 0-100%) |
| DELETE | `/{branch_id}/job/{job_id}` | 작업 취소 |
| GET | `/{branch_id}/pdf` | PDF 다운로드 |

### 페이지 라우트
| Path | Description |
|------|-------------|
| `/` | 메인 대시보드 |
| `/analysis` | 리뷰 분석 페이지 |
| `/tag-tester` | 태그 테스트 페이지 |

## Environment Variables

`.env` 파일 필수:
```
OPENAI_API_KEY=sk-...
LLM_PROVIDER=openai
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...
API_PREFIX=/api  # 로컬: /api, 서버: /review/api
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
Request → API (endpoints) → Service → Domain/Repository → Response
                              ↓
                         Infrastructure (LLM)
```

| Layer | 역할 |
|-------|------|
| `api/` | HTTP 요청/응답 처리 |
| `services/` | API 비즈니스 로직 |
| `domain/` | 핵심 도메인 로직 (분석, 파이프라인) |
| `infrastructure/` | 외부 시스템 (LLM) |
| `repository/` | DB 접근 |
| `models/` | DB 테이블 매핑 |
| `schemas/` | API 요청/응답 DTO |

## Code Principles

1. **단일 책임**: 하나의 파일/함수는 하나의 역할
2. **의존성 주입**: `deps.py`에서 서비스 생성
3. **Repository 패턴**: Repository로 DB 접근 추상화
4. **DTO 패턴**: 데이터 전송 객체로 타입 안전성 보장
5. **순환 참조 방지**: 함수 내부 import 사용
6. **에러 처리**: HTTPException으로 적절한 에러 응답
7. **로깅**: logging 모듈로 에러 상황 기록

## Git Rules

- **main/master 브랜치에 직접 푸시 금지**: 절대로 root 브랜치(main, master)에 직접 push하지 말 것. 반드시 feature 브랜치에서 작업 후 PR을 통해 병합할 것.

## Database Tables

| 테이블 | 용도 |
|--------|------|
| `branch_summaries` | 지점별 요약 데이터 |
| `branch_reviews` | 원본 리뷰 데이터 |
| `recent_reviews` | 최근 리뷰 캐시 |
| `branch_tags` | 지점별 태그 매핑 |
| `tags` | 태그 마스터 |
| `sentiment_stats` | 감정 통계 |
| `affiliates` | 업체 정보 |
| `branch_reports` | AI 리포트 저장 |
| `report_jobs` | 비동기 작업 상태 (pending/processing/completed/failed) |

## 비동기 작업 패턴 (502 타임아웃 방지)

긴 처리 시간(60초+) 작업은 백그라운드 + 폴링 패턴 사용:
```
POST /generate/async → job_id 즉시 반환
GET  /job/{job_id}   → 2초 간격 폴링 (progress: 0-100%)
```

## 개발 명령어

- `python -m py_compile <file.py>` - Python 문법 검사
- Supabase MCP로 마이그레이션: `mcp__supabase__apply_migration`
