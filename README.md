# Review Summary AI

Carmore 렌트카 리뷰를 자동 분석하고 요약하는 운영팀용 대시보드 시스템.

22만 건 이상의 고객 리뷰를 NLP로 분석하여 태그 분류, 감정 판단, AI 요약 리포트를 생성한다.

---

## 목차

- [빠른 시작](#빠른-시작)
- [시스템 요구사항](#시스템-요구사항)
- [환경변수](#환경변수)
- [실행 방법](#실행-방법)
- [테스트](#테스트)
- [주요 기능](#주요-기능)
- [아키텍처](#아키텍처)
- [프로젝트 구조](#프로젝트-구조)
- [API 요약](#api-요약)
- [페이지](#페이지)
- [운영 스크립트](#운영-스크립트)
- [배포](#배포)

---

## 빠른 시작

```bash
# 1. 클론
git clone https://github.com/teamo2dev/Review_Summary_AI.git
cd Review_Summary_AI

# 2. 의존성 설치 (uv 필요)
uv sync

# 3. 환경변수 설정
cp .env.template .env
# .env 파일을 열어 값 채우기 (아래 '환경변수' 섹션 참조)

# 4. 개발 서버 실행
make dev
# → http://localhost:8000
```

---

## 시스템 요구사항

| 항목 | 요구사항 |
|------|----------|
| Python | 3.12 이상 |
| 패키지 매니저 | [uv](https://docs.astral.sh/uv/) |
| DB | PostgreSQL (asyncpg 드라이버) |
| OS 패키지 (PDF 생성 시) | `fonts-nanum`, `libpango`, `libcairo2` 등 |

> PDF 생성이 필요 없는 로컬 개발에서는 OS 패키지 없이 실행 가능하다.
> Docker를 사용하면 모든 의존성이 자동으로 설치된다.

---

## 환경변수

`.env.template`을 복사하여 `.env` 파일을 만들고 아래 값을 채운다.

### 필수

| 변수 | 설명 | 예시 |
|------|------|------|
| `DATABASE_URL` | PostgreSQL 접속 URL | `postgresql+asyncpg://user:pass@localhost:5432/reviewdb` |
| `OPENAI_API_KEY` | OpenAI API 키 | `sk-...` |
| `INTERNAL_API_KEY` | 내부 API 인증 키 | 임의 문자열 |
| `PUBLIC_API_KEY` | 외부 Public API 인증 키 | 임의 문자열 |

> `DATABASE_URL` 대신 `DATABASE_USER`, `DATABASE_PASSWORD`, `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`을 개별 설정해도 된다.

### 선택

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `LLM_PROVIDER` | `openai` | LLM 프로바이더 |
| `API_PREFIX` | `/api` | API 경로 접두사 (프로덕션: `/review/api`) |
| `AWS_ACCESS_KEY_ID` | - | AWS Athena용 |
| `AWS_SECRET_ACCESS_KEY` | - | AWS Athena용 |
| `AWS_REGION` | `ap-northeast-2` | AWS 리전 |
| `ATHENA_DATABASE` | `carmore` | Athena DB명 |
| `ATHENA_OUTPUT_BUCKET` | - | Athena 쿼리 결과 S3 버킷 |
| `N8N_API_KEY` | - | n8n 웹훅 인증 |
| `N8N_TEST_MODE` | `true` | n8n 웹훅 경로 (`true`: `/webhook-test`) |
| `CARMORE_ADMIN_URL` | `https://dev-admin.carmore.kr` | Carmore 관리자 URL |
| `LIGHTWEIGHT_MODE` | `false` | NLP 모델 프리로딩 생략 (메모리 절약) |

---

## 실행 방법

### 로컬 개발 (hot-reload)

```bash
make dev
```

내부적으로 `uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`을 실행한다.

### Docker

```bash
# 빌드 + 실행 + 로그
make run

# 개별 명령
make build    # 이미지 빌드
make up       # 컨테이너 실행
make down     # 컨테이너 중지
make logs     # 로그 확인
make clean    # 이미지 + 컨테이너 정리
```

컨테이너 사양: CPU 1코어, 메모리 1024MB, 포트 8000.

### DB 마이그레이션

```bash
# 마이그레이션 적용
alembic upgrade head

# 새 마이그레이션 생성
alembic revision --autogenerate -m "설명"
```

---

## 테스트

```bash
# 전체 테스트
pytest

# 특정 파일
pytest tests/test_sentiment_core.py

# 상세 출력
pytest -v
```

주요 테스트 카테고리:

| 카테고리 | 파일 | 내용 |
|----------|------|------|
| 감정 분석 | `test_sentiment_core.py`, `test_sentiment_patterns.py` | 규칙 패턴, 이중부정, 반전 구문 |
| 태그 분류 | `test_hybrid_classifier.py`, `test_absa.py` | 하이브리드 분류, ABSA |
| 파이프라인 | `test_integration_pipeline.py` | 전처리 ~ 통계 집계 E2E |
| API 계약 | `test_schema_contract.py`, `test_dto_snapshot.py` | 스키마 유효성, 응답 형태 |
| 리포트 | `test_report_service_integration.py` | 리포트 생성/캐싱/작업 관리 |
| 에지 케이스 | `test_edge_cases_fuzz.py`, `test_regression.py` | 퍼징, 회귀 방지 |

---

## 주요 기능

### 리뷰 분석 파이프라인

리뷰 텍스트를 입력받아 아래 순서로 처리한다:

```
리뷰 텍스트
  → 전처리 (정규화, 불용어 제거)
  → 형태소 분석 (Kiwi)
  → 키워드 추출
  → 태그 분류 (규칙 + 임베딩 유사도)
  → 감정 판단 (규칙 + 문맥 분석)
  → 통계 집계 (지점별, 월별, 차량별)
```

### 태그 시스템

- **7개 카테고리**: 직원이 친절함, 사고 처리를 잘해줌, 주유비 부담 없음, 가격이 저렴함, 차량이 청결함, 차량외관이 좋음, 배달 서비스가 우수함
- **52개 세분화 태그**: 각 카테고리 하위에 매핑
- **1개 일반 fallback**: 분류 불가 시 "일반" 태그 할당

분류 방식: 규칙 기반 패턴 매칭 우선, 미매칭 시 FastEmbed 임베딩 유사도(임계값 0.50)로 보완.

### 감정 분석

하이브리드 방식으로 리뷰 내 키워드별 감정(긍정/부정/중립)을 판단한다.

- **규칙 기반**: 100+ 부정 키워드 패턴 (`불친절`, `비싸`, `냄새` 등)
- **문맥 분석**: 키워드 앞뒤 50자 윈도우
- **이중부정 처리**: `불편함이 없다` → 긍정
- **반전 구문 처리**: `~지만`, `~는데` → 뒷절 감정 우선

### AI 요약 / 리포트

- **요약**: GPT-4o-mini로 지점별 기간 요약 생성 (1개월/3개월/6개월/1년/전체)
- **리포트**: 비동기 생성 (job_id → 폴링), PDF 다운로드
- **캐시 무효화**: 신규 리뷰 30건 이상, 태그 비율 15% 변동, 감정 drift 8% 초과 시

### 자동 동기화

- 외부 Carmore API에서 리뷰를 주기적으로 수집
- APScheduler 기반 크론 스케줄링 (기본: 매일 06:00)
- n8n 웹훅 연동으로 워크플로우 트리거

---

## 아키텍처

```
Request → API (endpoints) → Service → Domain / Repository → Response
                               ↓
                          Infrastructure (LLM, PDF, Athena)
```

### 레이어 역할

| 레이어 | 역할 | 경로 |
|--------|------|------|
| **API** | HTTP 라우팅, 요청/응답 직렬화, 인증 | `app/api/v1/endpoints/` |
| **Service** | 비즈니스 로직, 트랜잭션 조정 | `app/services/` |
| **Domain** | 핵심 NLP 분석, 파이프라인 처리 | `app/domain/` |
| **Repository** | DB 접근 추상화 (SQLAlchemy Async) | `app/repository/` |
| **Infrastructure** | 외부 시스템 (OpenAI, AWS, PDF) | `app/infrastructure/` |

### 기술 스택

| 영역 | 기술 |
|------|------|
| Backend | Python 3.12, FastAPI, Uvicorn |
| NLP | Kiwi (형태소 분석), FastEmbed (ONNX 임베딩) |
| LLM | OpenAI GPT-4o-mini |
| DB | PostgreSQL, SQLAlchemy Async, asyncpg |
| PDF | WeasyPrint (프로덕션), fpdf2 (한글 폰트) |
| Scheduler | APScheduler, croniter |
| Data | pandas, openpyxl, NumPy |
| Frontend | Jinja2 템플릿, Vanilla JS |
| Infra | Docker, GitHub Actions, AWS (Athena) |

---

## 프로젝트 구조

```
app/
├── main.py                          # FastAPI 진입점, lifespan
├── api/v1/
│   ├── api.py                       # 라우터 등록
│   └── endpoints/                   # 18개 라우트 파일
│       ├── summaries.py             #   요약 CRUD, 승인
│       ├── report.py                #   리포트 조회, PDF
│       ├── report_generate.py       #   리포트 비동기 생성
│       ├── tags.py                  #   태그 관리
│       ├── sentiment.py             #   감정 통계
│       ├── analysis.py              #   리뷰 필터/검색
│       ├── sync.py                  #   리뷰 동기화
│       ├── pipeline_console.py      #   파이프라인 콘솔
│       ├── upload.py                #   Excel/CSV 업로드
│       ├── auth.py                  #   로그인/로그아웃
│       ├── pages.py                 #   HTML 페이지 라우트
│       ├── public_report.py         #   Public API (리포트)
│       └── ...
├── services/                        # 비즈니스 로직 (14개 서비스)
├── domain/
│   ├── analysis/                    # NLP 분석 모듈
│   │   ├── patterns.py              #   감정 패턴 (120+ 규칙)
│   │   ├── hybrid_classifier.py     #   규칙 + 임베딩 분류
│   │   ├── sentiment_core.py        #   감정 분석 핵심
│   │   ├── absa.py                  #   Aspect-Based Sentiment
│   │   ├── extractor.py             #   키워드 추출
│   │   └── tag_embeddings.py        #   임베딩 유사도
│   └── pipeline/                    # 배치/실시간 파이프라인
│       ├── unified_pipeline.py      #   배치 처리
│       ├── realtime_pipeline.py     #   단건 실시간 처리
│       └── steps/                   #   파이프라인 단계별 모듈
├── infrastructure/
│   ├── llm/                         # OpenAI 연동
│   ├── pdf/                         # PDF 생성
│   ├── athena/                      # AWS Athena 쿼리
│   └── storage/                     # 파일 스토리지
├── repository/                      # DB 접근 (11개 리포지토리)
├── models/                          # Pydantic DB 모델
├── schemas/                         # API 요청/응답 DTO
├── core/
│   ├── config.py                    # 환경 설정 (pydantic-settings)
│   ├── constants.py                 # 상수 (임계값, 모델명 등)
│   ├── container.py                 # DI 컨테이너
│   └── middleware.py                # 요청 추적
├── templates/                       # HTML 대시보드 (Jinja2)
├── static/                          # CSS, JS
└── scripts/                         # 운영 스크립트
tests/                               # 26개 테스트 파일
ddl/                                 # DB 마이그레이션 SQL
```

---

## API 요약

서버 실행 후 `http://localhost:8000/docs`에서 Swagger UI로 전체 API를 확인할 수 있다.

### 핵심 엔드포인트

| 그룹 | 메서드 | 경로 | 설명 |
|------|--------|------|------|
| **요약** | GET | `/api/v2/summaries` | 요약 목록 (필터/정렬) |
| | GET | `/api/v2/summaries/{id}` | 요약 상세 |
| | POST | `/api/v2/summaries/{id}/regenerate` | AI 재생성 |
| **리포트** | POST | `/api/v2/report/{id}/generate/async` | 비동기 리포트 생성 |
| | GET | `/api/v2/report/{id}/job/{job_id}` | 작업 상태 폴링 |
| | GET | `/api/v2/report/{id}/pdf` | PDF 다운로드 |
| **태그** | GET | `/api/tags/list` | 태그 목록 |
| | POST | `/api/tags/analyze-tags` | 텍스트 태그 분석 |
| **감정** | GET | `/api/sentiment/stats` | 지점별 감정 통계 |
| **분석** | GET | `/api/analysis/reviews` | 필터링 리뷰 조회 |
| | GET | `/api/analysis/reviews/export` | Excel 내보내기 |
| **동기화** | POST | `/api/sync/reviews` | 리뷰 동기화 실행 |
| **Public** | GET | `/public/report/{branch_id}` | 외부 리포트 (X-API-Key) |

### 인증 방식

| 대상 | 방식 |
|------|------|
| 대시보드 페이지 | 세션 기반 (`POST /login`) |
| 내부 API | `INTERNAL_API_KEY` 헤더 |
| Public API | `X-API-Key` 헤더 |

---

## 페이지

| URL | 설명 |
|-----|------|
| `/login` | 로그인 |
| `/` | 메인 대시보드 - 지점 요약 목록, 통계, 리포트 |
| `/analysis` | 리뷰 분석 - 필터링, 검색, Excel 내보내기 |
| `/pipeline` | 파이프라인 콘솔 - 배치/지역별 처리 모니터링 |
| `/scheduler` | 스케줄러 관리 - 워크플로우, 그룹 관리 |
| `/tag-tester` | 태그 테스트 - 텍스트 입력 → 태그/감정 결과 확인 |

---

## 운영 스크립트

```bash
# 전체 파이프라인 실행 (전처리 ~ 통계 집계)
python app/scripts/run_full_pipeline.py

# 지역별 파이프라인
python app/scripts/run_region_pipeline.py

# 배치 요약 생성
python app/scripts/run_batch_summary.py

# 키워드-태그 자동 매핑
python app/scripts/run_auto_mapping.py

# 리뷰 재태깅 (app/ 디렉토리에서 실행)
cd app && ../.venv/bin/python scripts/retag_reviews.py

# CSV 데이터 임포트
python app/scripts/import_from_csv.py

# 잘못 매핑된 리뷰 정리
python app/scripts/cleanup_misrouted_reviews.py
```

---

## 배포

### CI/CD (GitHub Actions)

`main` 브랜치에 push하면 자동 배포된다.

```
Push to main
  → Docker 이미지 빌드 (ghcr.io/teamo2dev/review-api)
  → AWS Bastion 경유 SSH 접속
  → 프로덕션 서버에서 docker compose up -d
```

### 수동 배포

```bash
# 이미지 빌드
docker build -t ghcr.io/teamo2dev/review-api:latest .

# 프로덕션 서버에서
docker compose -f docker-compose.prod.yml up -d
```

### 프로덕션 환경

| 항목 | 값 |
|------|-----|
| 레지스트리 | `ghcr.io/teamo2dev/review-api` |
| 포트 | 8000 |
| CPU / 메모리 | 1코어 / 1024MB |
| 네트워크 | `n8n-cloud-tm2-network` (외부) |
| API 접두사 | `/review/api` (Nginx 프록시) |

---

## 데이터베이스

27개 테이블, 22만 건 이상 리뷰 데이터.

| 그룹 | 주요 테이블 | 건수 |
|------|------------|------|
| 핵심 데이터 | `branch_reviews`, `branches`, `affiliates` | 222K, 1.4K, 390 |
| AI 요약 | `branch_summaries`, `branch_reports`, `report_jobs` | 1.5K, 152, 170 |
| 태그 | `tags`, `categories`, `keyword_mappings`, `review_tag_mappings` | 59, 7, 15.9K, 384K |
| 통계 | `branch_tags`, `monthly_*_stats` | 35K, 6.3K~64K |
| 차량 | `car_models_master`, `branch_car_models` | 553, 6.2K |

상세 스키마는 `.claude/docs/database-schema.md` 참조.

---

## License

Private - Carmore Internal Use Only
