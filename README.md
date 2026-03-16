# Review Summary AI

Carmore 렌트카 리뷰 요약 시스템 - 운영팀 모니터링 대시보드

## Overview

렌트카 서비스 리뷰를 자동으로 분석하고 요약하는 AI 기반 대시보드 시스템입니다.

### 주요 기능

- **리뷰 분석**: 한국어 형태소 분석(Kiwi) + 임베딩 유사도(FastEmbed)를 통한 키워드 추출
- **감정 분석**: 규칙 기반 패턴 매칭 + 문맥 분석 하이브리드 분류 (이중부정, 반전 구문 처리)
- **ABSA**: Aspect-Based Sentiment Analysis로 태그별 감정 판단
- **태그 분류**: 8개 카테고리, 52개 세분화 태그 + "일반" fallback
- **AI 요약/리포트**: GPT-4o-mini를 활용한 지점별 요약 및 PDF 리포트 생성
- **대시보드**: 운영팀용 모니터링, 분석, 파이프라인 콘솔, 스케줄러 관리
- **자동 동기화**: 외부 Carmore API 리뷰 자동 수집 및 처리
- **월간 스케줄러**: AI 리포트 자동 생성 예약, 그룹별 관리
- **Public API**: X-API-Key 인증 기반 외부 연동 API
- **인증 시스템**: 내부 API 키 + 세션 기반 페이지 인증
- **파이프라인 콘솔**: 배치/지역별 파이프라인 실행 및 모니터링
- **Excel 업로드**: CSV/Excel 파일을 통한 리뷰 일괄 등록

## Tech Stack

| Category | Technology |
|----------|------------|
| Backend | Python 3.12, FastAPI, Uvicorn |
| NLP | Kiwi (한국어 형태소 분석), FastEmbed (ONNX 임베딩) |
| LLM | OpenAI GPT-4o-mini |
| Database | PostgreSQL (SQLAlchemy Async + asyncpg) |
| PDF | WeasyPrint (프로덕션), fpdf2 (한글 폰트 지원) |
| Scheduler | APScheduler + croniter |
| Data | pandas, openpyxl, NumPy |
| AWS | Boto3 (Athena 쿼리) |
| Frontend | HTML, JavaScript (Vanilla), Jinja2 |
| Dev Tools | uv (패키지 매니저), Ruff (린터/포매터), pytest |

## Installation

### 1. 저장소 클론

```bash
git clone https://github.com/teamo2dev/Review_Summary_AI.git
cd Review_Summary_AI
```

### 2. 의존성 설치

```bash
uv sync
```

### 3. 환경변수 설정

`.env` 파일 생성:

```env
OPENAI_API_KEY=sk-...
LLM_PROVIDER=openai
DATABASE_URL=postgresql+asyncpg://user:pass@host:port/dbname
API_PREFIX=/api
PUBLIC_API_KEY=your-public-api-key
INTERNAL_API_KEY=your-internal-api-key
```

### 4. 실행

```bash
# 개발 서버 (hot-reload)
make dev

# 또는 직접 실행
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Pages

| URL | Description |
|-----|-------------|
| `/login` | 로그인 페이지 |
| `/` | 메인 대시보드 - 지점 요약 목록, 통계, 리포트 관리 |
| `/analysis` | 리뷰 분석 - 필터링, 검색, Excel 내보내기 |
| `/pipeline` | 파이프라인 콘솔 - 배치/지역별 파이프라인 실행 모니터링 |
| `/scheduler` | 스케줄러 관리 - 워크플로우 스케줄, 그룹 관리 |
| `/review-detail-test` | 리뷰 상세 테스트 페이지 |

## API

서버 실행 후 `/docs`에서 Swagger UI 확인 가능

### Core Resources

```
GET  /api/summaries                    # 요약 목록 (필터/정렬)
GET  /api/summaries/pending            # 보류 상태 요약
GET  /api/summaries/stats              # 전체 통계
GET  /api/summaries/{id}               # 요약 상세
PUT  /api/summaries/{id}               # 요약 수정 (상태 변경)
POST /api/summaries/{id}/regenerate    # 요약 재생성
```

### Reports

```
POST /api/reports/{id}/generate/async  # AI 리포트 비동기 생성
GET  /api/reports/{id}/job/{job_id}    # 작업 상태 폴링
GET  /api/reports/{id}                 # 리포트 조회
GET  /api/reports/{id}/pdf             # PDF 다운로드
GET  /api/reports/{id}/history         # 리포트 히스토리
DELETE /api/reports/{id}               # 리포트 삭제
```

### Tags & Sentiment

```
GET  /api/tags/list                    # 태그 목록
GET  /api/tags/categories              # 카테고리 목록
POST /api/tags/analyze-tags            # 텍스트 태그 분석
GET  /api/sentiment/stats              # 감정 통계 (지점별)
GET  /api/sentiment/stats/all          # 전체 감정 통계
```

### Analysis

```
GET  /api/analysis/filters             # 필터 옵션
GET  /api/analysis/reviews             # 필터링된 리뷰
GET  /api/analysis/reviews/export      # Excel 내보내기
```

### Sync & Processing

```
POST /api/sync/reviews                 # 리뷰 동기화 실행
GET  /api/sync/jobs/{id}               # 동기화 작업 상태
POST /api/realtime/process             # 단건 리뷰 실시간 처리
```

### Upload

```
POST /api/upload/...                   # Excel/CSV 파일 업로드
```

### Pipeline Console

```
POST /api/pipeline/...                 # 파이프라인 실행 및 상태 조회
```

### Presets

```
GET  /api/presets/...                   # 프리셋 관리
```

### n8n Webhooks & Scheduler

```
POST /api/n8n/review-sync              # n8n 리뷰 동기화 웹훅
POST /api/n8n/generate-summary         # n8n 요약 생성 웹훅
GET  /api/n8n/scheduler/workflows      # 스케줄러 워크플로우 목록
POST /api/n8n/scheduler/schedule       # 크론 스케줄 변경
POST /api/n8n/scheduler/toggle         # 워크플로우 활성화/비활성화
POST /api/n8n/scheduler/trigger        # 수동 실행
POST /api/n8n/scheduler/cron/validate  # 크론 표현식 검증
GET  /api/n8n/scheduler/branches       # 스케줄 대상 지점 목록
GET  /api/n8n/scheduler/groups/{id}    # 그룹별 지점 스케줄 조회
POST /api/n8n/scheduler/groups/{id}    # 그룹 생성
PUT  /api/n8n/scheduler/groups/{id}    # 그룹 수정
DELETE /api/n8n/scheduler/groups/{id}  # 그룹 삭제
```

### Authentication

```
POST /login                            # 로그인
POST /logout                           # 로그아웃
```

### Public API (X-API-Key 인증)

```
GET  /public/report/{branch_id}        # 외부용 AI 리포트
GET  /public/{branch_id}               # 외부용 지점 요약
```

## Architecture

```
Request → API (endpoints) → Service → Domain/Repository → Response
                              ↓
                         Infrastructure (LLM, PDF, Athena, Storage)
```

### 레이어 구조

| Layer | 역할 | 경로 |
|-------|------|------|
| API | 라우팅, 요청/응답 처리, 인증 | `app/api/v1/endpoints/` |
| Service | 비즈니스 로직 | `app/services/` |
| Domain | 핵심 도메인 (NLP, 파이프라인) | `app/domain/` |
| Repository | DB 접근 추상화 | `app/repository/` |
| Infrastructure | 외부 시스템 연동 | `app/infrastructure/` |

## Project Structure

```
app/
├── main.py                          # FastAPI 진입점, lifespan
├── api/v1/
│   ├── api.py                       # 라우터 등록
│   └── endpoints/
│       ├── summaries.py             # 요약 CRUD, 승인 워크플로우
│       ├── summary_branch.py        # 지점별 요약, 리뷰, 차량 태그
│       ├── report.py                # AI 리포트 조회, PDF, 히스토리
│       ├── report_generate.py       # AI 리포트 비동기 생성
│       ├── tags.py                  # 태그 관리
│       ├── sentiment.py             # 감정 통계
│       ├── analysis.py              # 리뷰 분석, 필터링
│       ├── sync.py                  # 리뷰 동기화
│       ├── realtime.py              # 실시간 처리
│       ├── upload.py                # Excel/CSV 업로드
│       ├── pipeline_console.py      # 파이프라인 콘솔
│       ├── presets.py               # 프리셋 관리
│       ├── n8n.py                   # n8n 웹훅 (동기화, 요약 생성)
│       ├── n8n_scheduler.py         # n8n 스케줄러 관리, 그룹 관리
│       ├── auth.py                  # 로그인/로그아웃, 세션 인증
│       ├── pages.py                 # HTML 페이지 라우트
│       ├── public_report.py         # Public API (리포트)
│       ├── public_summary.py        # Public API (요약)
│       └── deps.py                  # 의존성 주입
├── services/
│   ├── summary_service.py           # 요약 서비스 (쿼리/생성/승인 mixin)
│   ├── report_service.py            # 리포트 관리
│   ├── report_ai_generator.py       # AI 리포트 생성
│   ├── report_job_service.py        # 리포트 작업 관리
│   ├── report_cache_service.py      # 리포트 캐싱
│   ├── tag_service.py               # 태그 관리
│   ├── tag_stats_calculator.py      # 태그 통계 계산
│   ├── sentiment_service.py         # 감정 분석 서비스
│   ├── analysis_service.py          # 분석 서비스
│   ├── sync_service.py              # 리뷰 동기화
│   ├── sync_job_service.py          # 동기화 작업 관리
│   ├── pipeline_job_service.py      # 파이프라인 작업 관리
│   ├── upload_job_service.py        # 업로드 작업 관리
│   ├── carmore_service.py           # Carmore API 연동
│   ├── vehicle_analyzer.py          # 차량 분석
│   └── preset_service.py            # 프리셋 서비스
├── domain/
│   ├── analysis/                    # NLP 분석 모듈
│   │   ├── patterns.py              # 감정 패턴 (120+ 정규식)
│   │   ├── hybrid_classifier.py     # 하이브리드 태그/감정 분류
│   │   ├── tag_embeddings.py        # 임베딩 유사도 매칭
│   │   ├── sentiment_utils.py       # 감정 분석 유틸
│   │   ├── sentiment_core.py        # 감정 분석 핵심 로직
│   │   ├── absa.py                  # Aspect-Based Sentiment Analysis
│   │   ├── extractor.py             # 키워드 추출
│   │   ├── aggregator.py            # 분석 결과 집계
│   │   ├── chunker.py               # 텍스트 청킹
│   │   └── _singletons.py           # NLP 모델 싱글턴 관리
│   └── pipeline/                    # 처리 파이프라인
│       ├── pipeline.py              # BasePipeline (공통 NLP)
│       ├── unified_pipeline.py      # 배치 처리
│       ├── realtime_pipeline.py     # 실시간 단건 처리
│       └── steps/                   # 파이프라인 단계
│           ├── preprocessor.py      # 전처리
│           ├── keyword_manager.py   # 키워드 관리
│           ├── review_tag_mapper.py  # 리뷰-태그 매핑
│           ├── tag_aggregator.py    # 태그 집계
│           ├── car_model_tags.py    # 차량 모델 태그
│           ├── monthly_stats.py     # 월별 통계
│           ├── monthly_car_model_stats.py  # 월별 차량 모델 통계
│           ├── review_updater.py    # 리뷰 업데이트
│           └── decay_job.py         # 시간 감쇠 처리
├── infrastructure/
│   ├── llm/                         # LLM 프로바이더 (OpenAI)
│   ├── pdf/                         # PDF 생성 & 캐싱
│   ├── athena/                      # AWS Athena 연동
│   └── storage/                     # 파일 스토리지
├── repository/                      # DB 접근 레이어
│   ├── database.py                  # 엔진/세션 팩토리
│   ├── orm_models.py                # SQLAlchemy ORM 모델
│   ├── base.py                      # 베이스 리포지토리
│   ├── review_repository.py
│   ├── summary_repository.py
│   ├── report_repository.py
│   ├── report_job_repository.py
│   ├── tag_repository.py
│   ├── branch_tag_repository.py
│   ├── sentiment_repository.py
│   ├── car_model_repository.py
│   ├── affiliate_repository.py
│   ├── sync_metadata_repository.py
│   ├── new_review_repository.py
│   └── preset_repository.py
├── models/                          # Pydantic DB 모델
├── schemas/                         # API 요청/응답 DTO
├── core/
│   ├── config.py                    # 환경 설정
│   ├── constants.py                 # 상수 정의
│   ├── container.py                 # DI 컨테이너
│   ├── middleware.py                # 요청 추적 미들웨어
│   ├── response.py                  # TZAwareJSONResponse
│   ├── timezone.py                  # UTC/KST 유틸
│   ├── cache.py                     # 캐시 유틸
│   ├── decay.py                     # 시간 감쇠 함수
│   └── stopwords.py                 # 한국어 불용어
├── templates/                       # HTML 대시보드
│   ├── dashboard_v2.html            # 메인 대시보드
│   ├── analysis.html                # 리뷰 분석
│   ├── pipeline_console.html        # 파이프라인 콘솔
│   ├── scheduler.html               # 스케줄러 관리
│   ├── login.html                   # 로그인
│   ├── review_detail_test.html      # 리뷰 상세 테스트
│   └── pdf/report_template.html     # PDF 리포트 템플릿
├── static/
│   ├── js/shared-utils.js           # 공통 JS 유틸
│   └── css/shared-theme.css         # 공통 CSS 테마
└── scripts/                         # 유틸리티 스크립트
    ├── retag_reviews.py             # 리뷰 재태깅
    ├── run_auto_mapping.py          # 키워드 자동 매핑
    ├── run_full_pipeline.py         # 전체 파이프라인 실행
    ├── run_region_pipeline.py       # 지역별 파이프라인 실행
    ├── run_batch_summary.py         # 배치 요약 생성
    ├── import_from_csv.py           # CSV 데이터 임포트
    ├── cleanup_misrouted_reviews.py # 잘못 매핑된 리뷰 정리
    └── migrate_sentiments.py        # 감정 데이터 마이그레이션
```

## Key Constants

```python
OPENAI_RPM = 3500                # API Rate Limit
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
SIMILARITY_THRESHOLD = 0.35      # 태그 분류 최소 유사도
CONTEXT_WINDOW_SIZE = 50         # 감정 분석 문맥 윈도우 (글자)
```

## Docker

```bash
# 로컬 빌드 & 실행
make run

# 또는 개별 명령
docker build -t review-api:local .
docker-compose -f docker-compose.prod.yml up -d
```

컨테이너 사양: CPU 1.0코어, 메모리 1024MB, 포트 8000

## Scripts

```bash
# 키워드-태그 자동 매핑
python app/scripts/run_auto_mapping.py

# 리뷰 재태깅 (app/ 디렉토리에서 실행)
cd app && ../.venv/bin/python scripts/retag_reviews.py

# 전체 파이프라인 실행
python app/scripts/run_full_pipeline.py

# 지역별 파이프라인 실행
python app/scripts/run_region_pipeline.py

# 배치 요약 생성
python app/scripts/run_batch_summary.py

# CSV 데이터 임포트
python app/scripts/import_from_csv.py

# 감정 데이터 마이그레이션
python -m scripts.migrate_sentiments [--branch-id ID] [--dry-run]

# 문법 검사
python -m py_compile <file.py>

# DB 마이그레이션
alembic upgrade head
alembic revision --autogenerate -m "설명"
```

## License

Private - Carmore Internal Use Only
