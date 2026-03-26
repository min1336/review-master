# 리뷰 요약 시스템 — 기술 설계 문서

> 대상 독자: 이 프로젝트에 처음 합류하는 개발자
> 최종 수정: 2026-03-26

이 문서는 [Diataxis 프레임워크](https://docs.divio.com/documentation-system/)에 따라 4개 파트로 구성되어 있다.

| 파트 | 성격 | 언제 읽나 |
|------|------|-----------|
| **Part 1. 개요** | 이해 (Explanation) | 시스템이 뭔지 처음 파악할 때 |
| **Part 2. 시작하기** | 따라하기 (Tutorial) | 처음 로컬에서 돌려볼 때 |
| **Part 3. 레퍼런스** | 찾아보기 (Reference) | 특정 컴포넌트/로직을 확인할 때 |
| **Part 4. 가이드** | 문제 해결 (How-to) | 테스트 작성, 디버깅할 때 |

---

## 목차

**Part 1. 개요**

- [1.1 비즈니스 컨텍스트](#11-비즈니스-컨텍스트)
- [1.2 처리 흐름 요약](#12-처리-흐름-요약)
- [1.3 핵심 기능 5가지](#13-핵심-기능-5가지)
- [1.4 아키텍처](#14-아키텍처)
- [1.5 핵심 워크플로우](#15-핵심-워크플로우)

**Part 2. 시작하기**

- [2.1 Quick Start](#21-quick-start)
- [2.2 워크스루 예시](#22-워크스루-예시)
- [2.3 전체 흐름 시퀀스 다이어그램](#23-전체-흐름-시퀀스-다이어그램)

**Part 3. 레퍼런스**

- [3.1 서비스 계층 상세](#31-서비스-계층-상세)
- [3.2 도메인 분석 엔진](#32-도메인-분석-엔진)
- [3.3 파이프라인 3종](#33-파이프라인-3종)
- [3.4 데이터 모델](#34-데이터-모델)
- [3.5 설정](#35-설정)
- [3.6 DI 와이어링](#36-di-와이어링)
- [3.7 에러 처리 전략](#37-에러-처리-전략)
- [3.8 대시보드 UI](#38-대시보드-ui)

**Part 4. 가이드**

- [4.1 테스트 작성 가이드](#41-테스트-작성-가이드)
- [4.2 트러블슈팅](#42-트러블슈팅)
- [4.3 용어 사전](#43-용어-사전)

---

## Part 1. 개요

> 이 시스템은 무엇이고, 왜 이렇게 설계했는가

## 1.1 비즈니스 컨텍스트

Carmore 렌트카 플랫폼에 22만 건 이상의 고객 리뷰가 쌓여 있다. 운영팀은 지점별 서비스 품질을 모니터링하고 개선 방향을 도출해야 하지만, 리뷰를 수작업으로 분석하는 것은 불가능하다.

이 시스템은 리뷰를 자동으로 **수집 → 분석(감정/태그) → 요약 → 리포트** 생성하여, 운영팀이 대시보드에서 지점별 상태를 한눈에 파악할 수 있게 한다.

## 1.2 처리 흐름 요약

```text
Athena(리뷰 원본) → SyncService(동기화)
→ UnifiedPipeline(9단계 배치 분석)
  → 전처리 → 키워드 추출(Kiwi) → 감정 분석(ABSA+규칙+임베딩)
  → 태그 분류(HybridClassifier) → 집계 테이블 갱신
→ SummaryGenerator(AI 요약, GPT-4o-mini)
→ ReportService(컨설팅 리포트 + PDF)
→ 대시보드(HTML, 3개 페이지)
```

## 1.3 핵심 기능 5가지

| 기능 | 설명 | 주요 컴포넌트 |
|------|------|---------------|
| **리뷰 동기화** | Athena ↔ PostgreSQL 양방향 동기화 | SyncService, UnifiedPipeline |
| **감정 분석** | 리뷰별 긍정/부정/중립 판정 (규칙+임베딩+평점) | ABSA, HybridClassifier, UnifiedSentimentAnalyzer |
| **태그 분류** | 52개 세분화 태그로 리뷰 자동 분류 | HybridClassifier (규칙 O(1) + FastEmbed) |
| **AI 요약** | 지점별 기간 요약 (1m/3m/6m/1y/all) | SummaryGenerator, GPT-4o-mini |
| **컨설팅 리포트** | 4단계 파이프라인 + PDF 생성 | ReportService, ReportAIGenerator |

## 1.4 아키텍처

### 컴포넌트 의존성 다이어그램

```text
FastAPI (main.py)
├── API Layer (api/v1/endpoints/)
│   ├── summaries.py       ← 요약 CRUD
│   ├── tags.py            ← 태그 관리
│   ├── sentiment.py       ← 감정 통계
│   ├── analysis.py        ← 필터링 분석
│   ├── report.py          ← 리포트 생성/조회
│   └── pages.py           ← HTML 대시보드 라우트
│
├── Service Layer (services/)
│   ├── SummaryService         ← 요약 조회/수정/승인
│   │   └── SummaryGenerator   ← AI 요약 생성 (LLM 호출)
│   ├── ReportService          ← 리포트 오케스트레이터 (4단계)
│   │   ├── ReportAIGenerator  ← AI 리포트 텍스트 생성
│   │   ├── TagStatsCalculator ← 태그 통계 계산 (순수 함수)
│   │   ├── VehicleAnalyzer    ← 차량 모델별 분석
│   │   └── ReportCacheService ← CLT 기반 캐시 무효화
│   ├── SyncService            ← Athena ↔ PostgreSQL 동기화
│   │   └── UnifiedPipeline    ← 9단계 배치 파이프라인
│   ├── AnalysisService        ← 리뷰 검색/필터링
│   └── TagService             ← 태그 CRUD + 자동 매핑
│
├── Domain Layer (domain/)
│   ├── analysis/
│   │   ├── RuleBasedABSA      ← 절 단위 감정 분석
│   │   ├── HybridClassifier   ← 규칙+임베딩 태그 분류
│   │   ├── patterns.py        ← 200+ 한국어 감정 패턴
│   │   ├── ClauseChunker      ← 접속사 기반 절 분리
│   │   └── TagEmbeddingManager← FastEmbed ONNX 임베딩
│   └── pipeline/
│       ├── BasePipeline       ← 공통 (Kiwi, 전처리, 감정 분석)
│       ├── UnifiedPipeline    ← 배치 9단계 (동기화용)
│       └── RealtimePipeline   ← 실시간 단건 (N8N 웹훅용)
│
├── Infrastructure Layer
│   ├── llm/OpenAIProvider     ← GPT-4o-mini (RateLimiter 포함)
│   └── AthenaClient          ← AWS Athena 쿼리 (httpx)
│
└── Repository Layer (repository/)
    ├── database.py            ← AsyncEngine, 세션 팩토리, with_retry
    ├── orm_models.py          ← SQLAlchemy ORM 모델
    ├── SummaryRepository
    ├── BranchReviewRepository
    ├── BranchTagRepository
    ├── TagRepository
    └── SentimentRepository
```

### 레이어 경계

```text
API (endpoints)        → Service 호출 (FastAPI Depends로 DI)
    ↓
Service (Orchestrator) → 컴포넌트 조합, 워크플로우 제어
    ↓
Domain (Analysis)      → 순수 비즈니스 로직 (감정 분석, 태그 분류)
    ↓
Infrastructure         → 외부 API 통신 (OpenAI, Athena, PostgreSQL)
```

**경계 규칙**: Domain 레이어는 외부 API를 직접 호출하지 않는다. 필요한 데이터는 Service가 주입하고, Domain은 계산만 담당한다.

## 1.5 핵심 워크플로우

**주요 메서드 반환 타입:**

| 메서드 | 반환 타입 | 의미 |
|--------|-----------|------|
| `SyncService.sync_reviews()` | `SyncResultResponse` | 동기화 결과 (synced, new, processed 건수) |
| `UnifiedPipeline.run()` | `PipelineResultDTO` | 9단계 처리 결과 (성공/실패 단계별 상세) |
| `SummaryGenerator.generate_summary_with_data()` | `dict` | `{"success": bool, "summary": str, "period": str, ...}` |
| `ReportService.generate_report_with_progress()` | `ReportData` | 완성된 리포트 (Pydantic 모델) |
| `HybridClassifier.classify_review()` | `dict[str, dict]` | `{태그명: {"positive": [...], "negative": [...], ...}}` |

### `sync_reviews()` — 리뷰 동기화 진입점

```text
sync_reviews(progress_callback, date_from, date_to)
│
├─ Athena 클라이언트 확인
│  └─ 미설정 → ValueError("Athena 클라이언트가 설정되지 않았습니다")
│
├─ 날짜 범위를 1일 단위 청크로 분할
│
└─ for each day_chunk:
   └─ _process_day_chunk(chunk_since, chunk_until, day_idx, total_days, callback)
      │
      ├─ AthenaClient.fetch_reviews(since, until)
      │  └─ AWS Athena에서 해당 날짜 리뷰 조회
      │
      ├─ 중복 제거 (review_id 기준)
      │
      ├─ 오배정 필터링 (branch_id당 다수 업체 80% 기준)
      │
      ├─ branch_reviews UPSERT (데드락 방지: 즉시 commit)
      │
      └─ UnifiedPipeline.run(new_reviews)
         └─ 9단계 분석 + 집계 테이블 갱신
```

### `UnifiedPipeline.run()` — 9단계 배치 처리

```text
run(reviews, progress_callback)
│
├─ Step 1: ReviewPreprocessor (동기, asyncio.to_thread)
│  ├─ ReviewDTO.from_athena_row() 변환
│  ├─ 전처리 (욕설/광고 필터링)
│  ├─ Kiwi 키워드 추출
│  ├─ UnifiedSentimentAnalyzer 감정 분석
│  └─ HybridClassifier 태그 분류
│  → ProcessedReviewDTO[]
│
├─ Step 2: ReviewSentimentUpdater
│  └─ branch_reviews.sentiment 배치 UPDATE
│
├─ Step 4: TagAggregator
│  ├─ keyword_mappings 저장 (새 키워드 자동 매핑)
│  └─ branch_tags 갱신 (positive/negative/neutral_count)
│
├─ Step 5: CarModelTagAggregator
│  └─ car_models_master + branch_car_models 갱신
│
├─ Step 6: KeywordManager
│  └─ branch_keywords 빈도 갱신
│
├─ Step 7: ReviewTagMapper
│  └─ review_tag_mappings 저장
│
├─ Step 8: MonthlyStatsUpdater
│  └─ monthly_rating/sentiment/tag_stats 갱신
│
└─ Step 9: MonthlyCarModelStatsUpdater
   └─ monthly_car_model_tag_stats 저장

→ PipelineResultDTO(success, processed_reviews, steps[], total_duration)
```

### `generate_summary_with_data()` — AI 요약 생성

```text
generate_summary_with_data(branch_id, save_to_db, mode)
│
├─ _select_period_and_fetch_reviews(branch_id)
│  ├─ 기간 선택 (1m → 3m → 6m → 1y → all, 30건 이상인 첫 기간)
│  └─ 리뷰 부족(전체 30건 미만) → {"success": false, "error": "리뷰 부족"}
│
├─ _fetch_tag_and_sentiment_data(branch_id, period)
│  └─ 태그 통계 + 감정 통계 조회
│
├─ _fetch_representative_reviews(session, branch_id, start_date, mode)
│  └─ 감정별 대표 리뷰 샘플링
│
├─ _call_llm(branch_name, reviews, tags, sentiments, mode)
│  ├─ 프롬프트 구성 (마케팅/운영 모드 구분)
│  └─ OpenAI GPT-4o-mini 호출
│
├─ _postprocess_summary(branch_id, summary, mode)
│  ├─ 마크다운 제거 (#, *, **, ```)
│  └─ 숫자 검증 (할루시네이션 교정)
│
└─ save_to_db → branch_summaries 테이블 UPDATE
```

### `generate_report_with_progress()` — 4단계 리포트 생성

```text
generate_report_with_progress(branch_id, start_date, end_date, progress_callback, config)
│
├─ Step 1: _step_collect (10%)
│  ├─ 지점 정보 (이름, 지역, 리뷰수, 평점)
│  ├─ VehicleAnalyzer (차량 모델별 분석)
│  └─ 리뷰 원본 샘플
│
├─ Step 2: _step_tags (35%)
│  └─ TagStatsCalculator.compute()
│     ├─ RPC getTagStatsByPeriod → fallback branch_tags
│     ├─ 카테고리별 집계 (7개)
│     ├─ 강점/개선점 판정 (긍정비율/부정비율 기준)
│     └─ 태그별 순위 (top positive/negative)
│
├─ Step 2.5: _step_insights (55%)
│  ├─ 이전 기간 대비 트렌드 (up/down/stable)
│  ├─ 벤치마크 (동일 지역 평균 대비)
│  └─ 우선순위 액션 산출 (ACTION_SUGGESTIONS 매핑)
│
├─ Step 3: _step_ai (80%)
│  └─ ReportAIGenerator.generate_all()
│     ├─ _generate_period_summary() → LLM 호출
│     ├─ DB 저장 요약 우선 사용 (토큰 절약)
│     └─ 숫자 할루시네이션 교정 (±5% 임계값)
│
└─ Step 4: _step_build (100%)
   ├─ ReportData 조립 (Pydantic 모델)
   ├─ DB 저장 (branch_reports)
   └─ PDF 생성 (선택)
```

---

## Part 2. 시작하기

> 처음 합류했을 때 따라해보기

## 2.1 Quick Start

```bash
# 1. 의존성 설치
uv sync

# 2. .env 파일 설정 — 필수 항목:
#    DATABASE_URL                  (PostgreSQL 접속)
#    OPENAI_API_KEY                (AI 요약/리포트)
#    LLM_PROVIDER=openai           (LLM 프로바이더)
#    API_PREFIX=/api               (로컬) 또는 /review/api (서버)

# 3. (선택) Athena 동기화를 활성화하려면 추가:
#    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
#    ATHENA_DATABASE, ATHENA_OUTPUT_BUCKET

# 4. DB 마이그레이션
uv run alembic upgrade head

# 5. 로컬 개발 서버
make dev
# → http://localhost:8000 (대시보드)
# → http://localhost:8000/analysis (리뷰 분석)
# → http://localhost:8000/tag-tester (태그 테스트)
```

> **Tip**: Athena 없이도 대시보드와 요약 기능은 동작한다. 이미 PostgreSQL에 리뷰 데이터가 있으면 Athena 설정 없이 요약 생성/리포트 생성을 테스트할 수 있다.

## 2.2 워크스루 예시

실제 데이터로 리뷰 분석이 어떻게 진행되는지 처음부터 끝까지 따라가본다.

**상황**: 고객이 "제주공항점"에 다음 리뷰를 작성했다.

```text
[입력 데이터]
  리뷰: "직원이 친절했지만 차량이 더러웠어요. 가격은 합리적이었습니다."
  별점: 서비스 4.5, 차량 2.0, 편의성 4.0
  지점: 제주공항점 (branch_id=101)

[1단계: 절 청킹 (ClauseChunker)]
  입력: "직원이 친절했지만 차량이 더러웠어요. 가격은 합리적이었습니다."
  결과: ["직원이 친절했지만", "차량이 더러웠어요", "가격은 합리적이었습니다"]

[2단계: 키워드 추출 (Kiwi)]
  형태소 분석 → NNG/NNP/VA/VV 필터링 → stopword 제거
  결과: ["직원", "친절", "차량", "더러", "가격", "합리"]

[3단계: ABSA 분석 (절별)]
  절1: "직원이 친절했지만"
    → Aspect: "직원친절" (키워드: "친절")
    → Sentiment: positive (confidence: 0.95)
  절2: "차량이 더러웠어요"
    → Aspect: "청결" (키워드: "더러")
    → Sentiment: negative (confidence: 0.90)
  절3: "가격은 합리적이었습니다"
    → Aspect: "가격" (키워드: "합리")
    → Sentiment: positive (confidence: 0.85)

[4단계: 하이브리드 분류 (HybridClassifier)]
  "친절" → 규칙 매칭(O(1)) → "직원친절" (1.0)
  "더러" → 규칙 매칭(O(1)) → "청결" (1.0)
  "합리" → 규칙 매칭(O(1)) → "가격" (1.0)
  "직원" → 임베딩 유사도 0.45 < 0.50 → "기타" (스킵)
  "차량" → 범용 키워드 → 규칙만 시도 → 미매핑 (스킵)

[5단계: 충돌 해소]
  양보 구문 "~지만" 감지 → CONCESSION_REGEX 매칭
  "직원친절": positive=[친절], negative=[] → 유지
  "청결": positive=[], negative=[더러] → 유지
  "가격": positive=[합리], negative=[] → 유지

[6단계: 통합 감정 분석]
  텍스트 분석: mixed (positive 2, negative 1)
  평점 분석: min(2.0) < 3.0 → 부정 신호, avg(3.5) → 중립
  통합 규칙: min < 3.0 + 텍스트 mixed → "neutral" (confidence: 0.70)

[7단계: DB 저장]
  branch_reviews: sentiment = "neutral"
  branch_tags: "직원친절" positive_count +1
  branch_tags: "청결" negative_count +1
  branch_tags: "가격" positive_count +1
  monthly_sentiment_stats: neutral_count +1
```

**AI 요약 예시** — 같은 지점의 리뷰 100건을 요약하면:

```text
[AI 요약 입력]
  지점: 제주공항점, 리뷰 수: 156건 (최근 3개월)
  태그 통계: 직원친절(+87%), 청결(-23%), 가격(+65%)
  감정 분포: positive 68%, negative 15%, neutral 17%

[AI 요약 출력 (운영 모드)]
  "제주공항점은 최근 3개월간 156건의 리뷰에서 직원 친절도에 대한
  높은 만족도를 보이고 있습니다. 다만 차량 청결도에 대한 부정적
  피드백이 23%로, 차량 반납 후 세차 프로세스 개선이 필요합니다.
  가격 경쟁력은 긍정적으로 평가받고 있습니다."
```

## 2.3 전체 흐름 시퀀스 다이어그램

```mermaid
sequenceDiagram
    participant Athena as AWS Athena
    participant Sync as SyncService
    participant Pipeline as UnifiedPipeline
    participant Preproc as ReviewPreprocessor
    participant ABSA as RuleBasedABSA
    participant HC as HybridClassifier
    participant DB as PostgreSQL
    participant Summary as SummaryGenerator
    participant LLM as GPT-4o-mini
    participant Report as ReportService
    participant Dash as 대시보드

    Note over Sync: 매일 06:00 스케줄 또는 수동 트리거

    Sync->>Athena: fetch_reviews(since, until)
    Athena-->>Sync: [리뷰 raw data]

    Sync->>Sync: 중복 제거 + 오배정 필터링
    Sync->>DB: branch_reviews UPSERT

    Sync->>Pipeline: run(new_reviews)
    activate Pipeline

    Pipeline->>Preproc: process_batch(reviews)
    activate Preproc
    Note over Preproc: asyncio.to_thread (CPU-bound)

    loop 각 리뷰
        Preproc->>Preproc: 전처리 (욕설/광고 필터)
        Preproc->>Preproc: Kiwi 키워드 추출

        Preproc->>ABSA: analyze(review_text)
        ABSA-->>Preproc: [AspectOpinion, ...]

        Preproc->>HC: classify_review(text, keywords)
        HC-->>Preproc: {태그: {pos, neg, neutral}}

        Preproc->>Preproc: 통합 감정 판정
    end
    Preproc-->>Pipeline: ProcessedReviewDTO[]
    deactivate Preproc

    Pipeline->>DB: Step 2: sentiment 배치 UPDATE
    Pipeline->>DB: Step 4: branch_tags 갱신
    Pipeline->>DB: Step 5: car_models 갱신
    Pipeline->>DB: Step 6: branch_keywords 갱신
    Pipeline->>DB: Step 7: review_tag_mappings 저장
    Pipeline->>DB: Step 8: monthly_*_stats 갱신
    Pipeline->>DB: Step 9: monthly_car_model_tag_stats

    Pipeline-->>Sync: PipelineResultDTO
    deactivate Pipeline

    Note over Summary: 수동 트리거 (대시보드에서)

    Summary->>DB: 태그/감정 통계 조회
    Summary->>DB: 대표 리뷰 샘플링
    Summary->>LLM: 프롬프트 + 데이터
    LLM-->>Summary: 요약 텍스트
    Summary->>Summary: 후처리 (마크다운 제거, 숫자 검증)
    Summary->>DB: branch_summaries UPDATE

    Note over Report: 수동 트리거 (대시보드에서)

    Report->>DB: Step 1: 지점 정보 + 차량 분석
    Report->>DB: Step 2: 태그 통계 계산
    Report->>Report: Step 2.5: 트렌드/벤치마크/액션
    Report->>LLM: Step 3: AI 기간 요약
    LLM-->>Report: 요약 텍스트
    Report->>Report: Step 4: ReportData 조립
    Report->>DB: branch_reports 저장

    Dash->>DB: 요약/태그/감정/리포트 조회
    DB-->>Dash: JSON 응답
```

---

## Part 3. 레퍼런스

> 특정 컴포넌트나 로직을 찾아볼 때

## 3.1 서비스 계층 상세

### SummaryService

**역할**: 요약 조회/수정/승인 워크플로우 관리

**파일**: `app/services/summary_service.py`

**핵심 설계:**

- SummaryGenerator에 AI 요약 생성을 위임 (역할 분리)
- Athena Primary → Supabase Fallback 이중 경로 (리뷰 데이터 조회)
- 승인 워크플로우: `generate_pending_summary()` → `approve_pending_summary()` → `apply_pending_summary()`

**주요 메서드:**

| 메서드 | 반환 타입 | 설명 |
|--------|-----------|------|
| `get_summaries(filters)` | `list[dict]` | 필터링된 요약 목록 |
| `generate_summary_with_data(branch_id, save_to_db, mode)` | `dict` | AI 요약 생성 (SummaryGenerator 위임) |
| `generate_pending_summary(branch_id, period)` | `dict` | 승인 대기 요약 생성 |
| `approve_pending_summary(branch_id)` | `dict \| None` | 대기 요약 승인 |
| `apply_pending_summary(branch_id, period)` | `PendingSummaryResultDTO` | 특정 기간 요약 적용 |
| `get_branch_reviews(branch_id)` | `BranchReviewsDTO` | 지점 리뷰 상세 |
| `get_car_model_tags(branch_id, car_model)` | `BranchCarModelsDTO` | 차량 모델별 태그 |

---

### SummaryGenerator

**역할**: AI 요약 생성 전담 (기간 선택 → 리뷰 수집 → LLM 호출 → 후처리)

**파일**: `app/services/summary_generator.py`

**핵심 설계:**

- 기간 자동 선택: 1m → 3m → 6m → 1y → all 순으로 30건 이상인 첫 기간 선택
- 마케팅/운영 모드 구분 (프롬프트 톤 변경)
- 후처리: 마크다운 제거 + 숫자 할루시네이션 검증
- `MIN_REVIEWS_FOR_SUMMARY = 30` (미만이면 요약 불가)

---

### ReportService

**역할**: 맞춤형 컨설팅 리포트 생성 오케스트레이터 (4단계 파이프라인)

**파일**: `app/services/report_service.py`

**핵심 설계:**

- 4단계 파이프라인: collect → tags → insights → AI → build
- CLT(Change List Threshold) 기반 캐시 무효화: 새 리뷰 30건 이상 쌓이면 리포트 재생성
- 각 단계 실패 시 부분 리포트 반환 (전체 중단 아님)
- `ACTION_SUGGESTIONS` 매핑 테이블: 태그 상태 → 구체적 개선 액션

---

### ReportAIGenerator

**역할**: 리포트용 AI 텍스트 생성 (LLM 3회 호출)

**파일**: `app/services/report_ai_generator.py`

**핵심 설계:**

- DB 저장 요약 우선 사용 (토큰 절약)
- 숫자 할루시네이션 교정: LLM 응답 내 숫자를 실제 데이터와 ±5% 비교
- 금지어 제거 + 이모지 제거 후 재검증
- LLM 실패 시 fallback_summary (기본 텍스트) 반환

---

### SyncService

**역할**: Athena ↔ PostgreSQL 양방향 동기화 + 파이프라인 통합

**파일**: `app/services/sync_service.py`

**핵심 설계:**

- 1일 단위 청킹: 대용량 Athena 쿼리 최적화 + 진행률 세분화
- 오배정 필터링: branch_id당 다수 업체가 80% 미만이면 소수 업체 리뷰 제거
- Ghost review 정리: Athena에 없는데 PostgreSQL에만 있는 리뷰 삭제
- 데드락 방지: UPSERT 후 즉시 commit
- 메모리 해제: `gc.collect()` 호출

---

### AnalysisService

**역할**: 분석 페이지 필터 옵션 & 리뷰 검색 조회

**파일**: `app/services/analysis_service.py`

**핵심 설계:**

- TTLCache(300s) 필터 옵션 캐싱 (5분마다 갱신)
- 지역-지점 계층형 필터
- Athena 감정 후필터링: over-fetch 500건 → 감정으로 필터링 (Athena에는 감정 컬럼 없음)
- Excel 내보내기 지원 (openpyxl)

---

### TagService

**역할**: 태그 CRUD + 자동 키워드 매핑

**파일**: `app/services/tag_service.py`

**핵심 설계:**

- HybridClassifier를 활용한 자동 키워드 → 태그 매핑
- TTLCache(300s) 카테고리 캐싱
- 매핑 태그명 우선 → 카테고리명 fallback (`CATEGORY_DEFAULT_TAG`)
- `asyncio.to_thread`로 CPU-bound 분류 비동기화

---

### TagStatsCalculator

**역할**: 순수 함수 태그 통계 계산

**파일**: `app/services/tag_stats_calculator.py`

**핵심 설계:**

- 모든 계산 `@staticmethod` (순수 함수, 부작용 없음)
- RPC `getTagStatsByPeriod` primary → fallback `branch_tags "all"` 기간
- 강점 판정: 긍정 비율 ≥ `STRENGTH_POSITIVE_RATIO`
- 개선점 판정: 부정 비율 ≥ `IMPROVEMENT_NEGATIVE_RATIO`
- 트렌드 방향: up/down/stable (이전 기간 대비)
- 태그 부족(< `MIN_PERIOD_TAG_COUNT=3`) → 전체 기간 대체

---

## 3.2 도메인 분석 엔진

### RuleBasedABSA

**역할**: 절 단위 규칙 기반 Aspect-Based Sentiment Analysis

**파일**: `app/domain/analysis/absa.py`

**처리 과정:**

1. **절 청킹**: `ClauseChunker.chunk()` — 접속사/연결어미(`지만`, `는데`, `고`) 기준 분리
2. **절별 Aspect 추출**: `_find_aspects()` — `ASPECT_KEYWORDS` 테이블에서 키워드 매칭
3. **문맥 필요 키워드 처리**: `CONTEXT_REQUIRED_KEYWORDS` — 예: "늦" → ["배차", "차량", "픽업"] 중 하나 필수
4. **감정 판단**: `_determine_sentiment()` — 우선순위 기반 판정 (아래 상세)
5. **중복 제거 및 병합**: `_merge_results()` — 동일 aspect 통합, confidence 높은 것 우선

**감정 판정 우선순위:**

```text
[1] 이중부정 최우선 (0.95) — "불편하지 않다" → 긍정
[2] 부정어+긍정어 패턴 (0.85) — "친절하지 않다" → 부정
[3] 명확한 부정 키워드 (STRONG_NEGATIVE_KEYWORDS) — 다수결
[4] 긍정 예외 체크 (0.80) — "틀림없", "끄떡없"
[5] 긍정+없다 패턴 (0.90) — "친절...없다" → 부정
[6] 짧은 리뷰 부스트 (len < 30) — 명확한 감정 우선
[7] 일반 패턴 매칭 — POSITIVE_REGEX vs NEGATIVE_REGEX 다수결
[8] 반복 감지 — 긍정어 반복 ≥ 1.5배 → confidence += 0.15
[9] 문맥 기반 추론 — 강한/중간 긍정어별 신뢰도 분류
```

---

### HybridClassifier

**역할**: 하이브리드 태그 분류 (규칙 + ABSA + FastEmbed 임베딩)

**파일**: `app/domain/analysis/hybrid_classifier.py`

**분류 전략 계층 (우선순위):**

```text
키워드 입력
    ↓
[1] 범용 키워드 체크 (_GENERIC_KEYWORDS)
    └─ "상태", "필요", "감사" 등 → 규칙만 시도, 임베딩 스킵
    ↓
[2] 일반 긍정어 체크 (GENERAL_POSITIVE_KEYWORDS)
    └─ "좋", "만족", "최고", "추천" → 규칙만 시도
    ↓
[3] 규칙 기반 매핑 (_check_rule_based_mapping)
    ├─ [O(1)] 정확 일치: self._rule_exact_map
    ├─ [O(1)] 어간 일치: extract_stem() → 사전 재매칭
    └─ [O(N)] 부분 문자열 폴백: self._rule_substr_pairs
    ↓
[4] 임베딩 기반 분류 (FastEmbed + 코사인 유사도)
    ├─ 모델: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
    ├─ 배치 인코딩 → 행렬 연산 (N×52 유사도 매트릭스)
    └─ score < 0.50 → "기타" (SIMILARITY_THRESHOLD)
```

**리뷰 분류 흐름 (`classify_review`):**

```text
1. ABSA 분석 (우선) → absa_tag_groups
2. ABSA에서 분류된 키워드 수집 → absa_classified set
3. 미분류 키워드만 임베딩 분류 (배치)
4. 양보/반전 구문 감지 (CONCESSION_REGEX)
5. 충돌 해소 (pos+neg 공존 → 반전 구문이면 neg 제거, 아니면 다수결)
6. 카테고리별 키워드 수 상한 (MAX_KEYWORDS_PER_CATEGORY = 3)
```

---

### UnifiedSentimentAnalyzer

**역할**: 텍스트 감정 + 평점 감정을 통합하여 최종 판정

**핵심 통합 규칙:**

| 규칙 | 조건 | 결과 | 신뢰도 |
|------|------|------|--------|
| Rule 1 | min_rating < 3.0 | negative 또는 neutral | 0.95 / 0.70 |
| Rule 2 | 텍스트 = 평점 (합의) | consensus | 높은 신뢰도 유지 |
| Rule 3 | 텍스트=negative ∧ avg≥4.0 | neutral | 0.70 |
| Rule 4 | 텍스트=positive ∧ avg<3.5 | neutral | 0.60 |
| Rule 5 | 기타 | 텍스트 우선 | × 0.9 감쇄 |

**가중치:**

```text
WEIGHT_RULE_BASED = 0.3   (ABSA 30%)
WEIGHT_HYBRID = 0.4       (HybridClassifier 40%)
평점: 별도 규칙 기반 (특수 조건에서 override)
```

---

### 패턴 정의

**파일**: `app/domain/analysis/patterns.py`

**부정 패턴 (~120개):**

| 범주 | 예시 |
|------|------|
| 불- 접두사 | 불친절, 불편, 불쾌, 불만 |
| 비싸 관련 | 비싸, 비싼, 비쌌 |
| 부정 어근 | 늦, 느리, 더럽, 지저분, 낡, 오래 |
| 배차/시간 | 기다림, 기다리, 오래걸 |
| 가격 | 바가지, 과금, 추가요금, 손해 |
| 서비스 | 무시, 무성의, 사기, 복잡 |

**긍정 패턴 (~50개):**

| 범주 | 예시 |
|------|------|
| 서비스 | 친절, 상냥, 정성, 감사, 최고 |
| 차량 | 깨끗, 청결, 깔끔, 새차, 신차 |
| 가격 | 저렴, 합리, 가성비, 할인 |
| 기타 | 감동, 재방문, 잘해, 순조 |

**특수 패턴:**

| 패턴 | 유형 | 결과 |
|------|------|------|
| `불편.{0,10}없` | 이중부정 | 긍정 (0.95) |
| `나쁘지.{0,5}않` | 이중부정 | 긍정 (0.95) |
| `틀림없`, `끄떡없` | 긍정 예외 | 긍정 (0.80) |
| `지만\|는데\|반면\|다만` | 양보/반전 | 뒤쪽 감정 우선 |

---

## 3.3 파이프라인 3종

### 비교

| | BasePipeline | UnifiedPipeline | RealtimePipeline |
|---|---|---|---|
| **용도** | 추상 클래스 (공통 기능) | 배치 일괄 처리 | 실시간 단건 처리 |
| **사용 시점** | 상속용 | Athena 동기화 (매일/수동) | N8N 웹훅 (신규 리뷰 즉시) |
| **입력** | — | `list[dict]` (Athena 결과) | 단일 리뷰 dict |
| **처리 방식** | — | 9단계 savepoint 트랜잭션 | SQL-level 증분 UPDATE |
| **리뷰 저장** | — | SyncService가 선행 저장 | 안 함 (SyncService 담당) |
| **집계 방식** | — | 전체 재계산 | `ON CONFLICT DO UPDATE +1` |
| **출력** | — | `PipelineResultDTO` | `RealtimeResultDTO` |

### UnifiedPipeline 9단계 상세

| Step | 클래스 | 역할 | 실패 시 |
|------|--------|------|---------|
| 1 | ReviewPreprocessor | 전처리+키워드+감정+태그 (동기) | 전체 중단 |
| 2 | ReviewSentimentUpdater | sentiment 배치 UPDATE | 다음 단계 진행 |
| 4 | TagAggregator | tags + branch_tags 갱신 | Step 7,8,9 스킵 |
| 5 | CarModelTagAggregator | 차량 모델 갱신 | 다음 단계 진행 |
| 6 | KeywordManager | branch_keywords 갱신 | 다음 단계 진행 |
| 7 | ReviewTagMapper | review_tag_mappings 저장 | 다음 단계 진행 |
| 8 | MonthlyStatsUpdater | monthly_*_stats 갱신 | 다음 단계 진행 |
| 9 | MonthlyCarModelStatsUpdater | 차량 월별 태그 통계 | 종료 |

> Step 3은 현재 사용되지 않음 (번호 건너뜀). Step 4 실패 시 의존 단계(7, 8, 9)는 자동 스킵.

---

## 3.4 데이터 모델

### 입력 데이터

```python
# app/schemas/dto_review.py

@dataclass
class ReviewDTO:
    """리뷰 원본 데이터."""
    review_id: int | None
    branch_id: int
    branch_name: str
    company_name: str
    content: str | None
    rating_service: float | None
    rating_car: float | None
    rating_convenience: float | None
    review_date: datetime | None
    car_model: str | None
    rent_type: str | None

    def is_valid(self) -> bool:
        """branch_id 존재 여부"""

    @classmethod
    def from_athena_row(cls, row: dict) -> ReviewDTO | None:
        """Athena 쿼리 결과 → ReviewDTO 변환"""
```

### 분석 결과

```python
# app/domain/analysis/absa.py

@dataclass
class AspectOpinion:
    """ABSA 분석 결과 1건."""
    aspect: str           # 태그명: "직원친절", "청결" 등
    opinion: str          # 원문 절: "직원이 친절했고"
    sentiment: str        # "positive", "negative", "neutral"
    confidence: float     # 신뢰도 (0.0 ~ 1.0)
    keywords: list[str]   # 매칭된 키워드: ["친절"]

# HybridClassifier.classify_review() 반환값
{
    "직원친절": {
        "positive": ["친절", "상냥"],
        "negative": [],
        "neutral": []
    },
    "청결": {
        "positive": [],
        "negative": ["더러운"],
        "neutral": []
    }
}
```

### 파이프라인 결과

```python
# app/schemas/dto_pipeline.py

@dataclass
class ProcessedReviewDTO:
    """파이프라인 처리 완료된 리뷰."""
    review: ReviewDTO
    keywords: list[str]              # Kiwi 추출 키워드
    sentiment: str                   # "positive" | "negative" | "neutral"
    confidence: float                # 감정 신뢰도
    tag_sentiments: dict[str, dict]  # {태그명: {pos:[], neg:[], neutral:[]}}

@dataclass
class PipelineStepResultDTO:
    """파이프라인 단일 단계 결과."""
    step_name: str
    success: bool
    input_count: int
    output_count: int
    duration_seconds: float
    error_message: str | None

@dataclass
class PipelineResultDTO:
    """파이프라인 전체 결과."""
    success: bool
    total_reviews: int
    processed_reviews: int
    total_branches: int
    steps: list[PipelineStepResultDTO]
    total_duration_seconds: float
    error_message: str | None
```

### 태그 메타데이터

```python
# app/domain/analysis/patterns.py

@dataclass(frozen=True)
class TagMeta:
    keywords: list[str]  # ["친절", "상냥", "정성", "배려", ...]

@dataclass(frozen=True)
class CategoryMeta:
    group: str                    # "affiliate" 등
    description: str              # 카테고리 설명
    tags: dict[str, TagMeta]     # {태그명: TagMeta}
```

---

## 3.5 설정

### .env — 필수 환경변수

```text
DATABASE_URL=postgresql+asyncpg://user:pass@host:port/dbname
OPENAI_API_KEY=sk-...
LLM_PROVIDER=openai
API_PREFIX=/api                   # 로컬: /api, 서버: /review/api
```

### .env — 선택 환경변수

```text
# AWS Athena (동기화 기능)
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=ap-northeast-2
ATHENA_DATABASE=carmore
ATHENA_OUTPUT_BUCKET=s3://...

# OpenAI 상세
OPENAI_MODEL=gpt-4o-mini
OPENAI_RPM=3500                   # 분당 최대 요청
OPENAI_ORG_ID=...
OPENAI_PROJECT_ID=...

# N8N 웹훅
N8N_TEST_MODE=true                # true → /webhook-test, false → /webhook
N8N_API_KEY=...
N8N_BASE_URL=https://n8n-cloud.carmore.kr

# 스케줄러
SYNC_HOUR=6                       # 매일 동기화 시각
SYNC_MINUTE=0
```

### 주요 상수

| 상수 | 값 | 위치 | 용도 |
|------|-----|------|------|
| `SIMILARITY_THRESHOLD` | 0.50 | `domain/analysis/` | 임베딩 유사도 최소값 |
| `CONTEXT_WINDOW_SIZE` | 50 | `domain/analysis/` | 감정 분석 문맥 윈도우 (글자) |
| `EMBEDDING_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | `domain/analysis/` | FastEmbed 모델 |
| `MIN_REVIEWS_FOR_SUMMARY` | 30 | `services/summary_generator.py` | 요약 생성 최소 리뷰 수 |
| `OPENAI_RPM` | 3500 | `core/config.py` | OpenAI 분당 요청 제한 |
| `WEIGHT_RULE_BASED` | 0.3 | `domain/analysis/` | ABSA 감정 가중치 |
| `WEIGHT_HYBRID` | 0.4 | `domain/analysis/` | HybridClassifier 감정 가중치 |
| `MAX_KEYWORDS_PER_CATEGORY` | 3 | `domain/analysis/` | 리뷰당 태그별 최대 키워드 |

---

## 3.6 DI 와이어링

`app/api/v1/endpoints/deps.py`에서 FastAPI `Depends()`로 서비스를 생성한다.

### 와이어링 순서

```text
1. Database Session (가장 기초)
   └─ get_session() → AsyncSession

2. Repository 레이어 (리플렉션 기반 동적 팩토리)
   ├─ SummaryRepository(session)
   ├─ BranchTagRepository(session)
   ├─ BranchReviewRepository(session)
   ├─ TagRepository(session)
   ├─ SentimentRepository(session)
   ├─ ReportRepository(session)
   └─ ... (12개 Repository)

3. Service 레이어 (Repository 조립)
   ├─ SummaryService(summary_repo, branch_tag_repo, review_repo, sentiment_repo, athena_client)
   │   └─ SummaryGenerator 내부 생성
   ├─ ReportService(summary_repo, review_repo, tag_repo, report_repo, sentiment_repo, athena_client)
   │   ├─ ReportAIGenerator 내부 생성
   │   ├─ TagStatsCalculator 내부 생성
   │   └─ VehicleAnalyzer 내부 생성
   ├─ SyncService(review_repo, athena_client, sync_metadata_repo)
   │   └─ UnifiedPipeline 내부 생성
   ├─ AnalysisService(review_repo, summary_repo, athena_client, new_review_repo)
   └─ TagService(tag_repo, branch_tag_repo, category_repo, mapping_repo)
```

### 싱글톤 (서버 프로세스 수명)

```text
AthenaClient        → ServiceContainer.get_athena_client() (lazy, 1회 생성)
Kiwi                → _singletons.get_kiwi() (threading.RLock 보호)
HybridClassifier    → _singletons.get_hybrid_classifier() (Double-Checked Locking)
SentimentAnalyzer   → _singletons.get_sentiment_analyzer() (Double-Checked Locking)
```

> **Kiwi 멀티스레드 직렬화**: Kiwi 내부 C++ 상태가 멀티스레드 불안전 → `kiwi_tokenize()` 함수에 별도 `threading.Lock` 적용. `asyncio.to_thread()` 환경에서도 안전.

### Lifespan 이벤트 (main.py)

```text
Startup:
  1. DB 엔진 초기화 (asyncpg)
  2. 고아 작업 복구 (processing 상태 리포트 작업 정리)
  3. NLP 모델 프리로드 (Kiwi, HybridClassifier, SentimentAnalyzer)

Shutdown:
  1. httpx 클라이언트 종료
  2. DB 엔진 종료
```

---

## 3.7 에러 처리 전략

### 원칙: 단계별 격리 (Stage Isolation)

각 단계의 실패가 이전 단계의 성공을 되돌리지 않는다.

| 서비스 | 실패 시 동작 | 폴백 전략 |
|--------|-------------|----------|
| SyncService (청크 처리) | chunk_errors 누적 | 부분 성공 응답 |
| UnifiedPipeline (단계별) | PipelineStepResultDTO(success=False) | 다음 단계 진행 |
| SummaryGenerator (리뷰 부족) | `{"success": false}` | 에러 메시지 반환 |
| SummaryGenerator (LLM 실패) | Exception 포착 | "AI 요약 생성 실패" |
| ReportService (단계별) | warning 로깅 | 부분 리포트 반환 |
| ReportAIGenerator (LLM 실패) | Exception 포착 | fallback_summary (기본 텍스트) |
| AnalysisService (Athena 실패) | ConnectionError 포착 | Supabase 폴백 |
| TagService (중복) | IntegrityError | ValueError("중복된 이름") |
| HybridClassifier (임베딩 실패) | RuntimeError | 규칙만 사용 |
| ABSA (절 분석 실패) | Exception 포착 | 다음 절로 진행 |

### DB 연결 자동 재시도

```python
# app/repository/database.py
@with_retry(max_attempts=3, min_wait=0.5, max_wait=4.0)
# Exponential backoff: wait = min(0.5 * 2^attempt, 4.0)
# 대상: asyncpg 연결 오류, OperationalError, OSError
```

### 동시 실행 방지

```text
SyncService: sync_metadata 테이블 잠금 (DB 레벨)
ReportService: report_jobs 상태 관리 (processing → completed/failed)
```

---

## 3.8 대시보드 UI

### 페이지 구성

| 템플릿 | 경로 | 역할 |
|--------|------|------|
| `dashboard_v2.html` | `/` | 메인 대시보드 (지점별 요약, 태그, 감정, 즐겨찾기) |
| `analysis.html` | `/analysis` | 리뷰 분석 (필터링, 검색, Excel 내보내기) |
| `pipeline_console.html` | — | 파이프라인 콘솔 (동기화 진행 모니터링) |
| `scheduler.html` | — | 스케줄러 설정 |
| `review_detail_test.html` | — | 리뷰 상세 분석 테스트 |

### 보안 규칙

- `innerHTML` 대신 DOM API 사용 (XSS 방지)
- 동적 텍스트: `.textContent` 사용
- HTML 본문: `escapeHtml()` (`shared-utils.js`)
- HTML 속성: `escapeAttr()` (`shared-utils.js`)

### 비동기 작업 UI 패턴

```text
POST .../async → job_id
GET  .../job/{job_id} → status + progress (2초 간격 폴링)
최대 60회 폴링 → AbortController로 모달 닫기 시 취소
프론트엔드: updateReportProgress() 패턴
```

### 즐겨찾기 페이지네이션

- `localStorage`에 `dashboard_favorites` 키로 `branch_id[]` 저장
- 페이지당 고정 개수 (DEFAULT_PAGE_SIZE: 30)
- 즐겨찾기가 페이지 초과 시 다음 페이지로 이동
- offset 계산: `prevNormalShown = Math.max(0, (currentPage * pageSize) - favCount)`

---

## Part 4. 가이드

> 특정 작업을 수행할 때 참고

## 4.1 테스트 작성 가이드

### 테스트 구조

```text
tests/
├── conftest.py                          # 공통 Mock 픽스처
├── test_sentiment_core.py               # 감정 분석 단위 테스트
├── test_sentiment_patterns.py           # 패턴 매칭 테스트
├── test_hybrid_classifier.py            # 하이브리드 분류기
├── test_absa.py                         # ABSA 단위
├── test_absa_hybrid.py                  # ABSA+분류기 통합
├── test_integration_pipeline.py         # End-to-End 파이프라인
├── test_chunker.py                      # 절 분할
├── test_extractor.py                    # 키워드 추출
├── test_tag_aggregator_category.py      # 태그 집계
├── test_tag_stats_*.py                  # 통계 계산
├── test_property_invariants.py          # 불변성 검증
├── test_edge_cases_fuzz.py              # 엣지 케이스 / Fuzz
├── test_regression.py                   # 회귀 테스트
├── test_schema_contract.py              # DTO 계약 검증
└── test_dto_snapshot.py                 # Snapshot 테스트
```

### Mock 픽스처 (conftest.py)

```python
# Repository Mock — AsyncMock 패턴
@pytest.fixture
def mock_summary_repo() -> AsyncMock

@pytest.fixture
def mock_branch_tag_repo() -> AsyncMock

@pytest.fixture
def mock_review_repo() -> AsyncMock

# 테스트용 데이터
@pytest.fixture
def sample_branch_tags() -> list[FakeBranchTag]
```

### 테스트 DI 패턴

```python
# Mock 조립 → 서비스 생성자에 직접 주입
summary_repo = AsyncMock(spec=SummaryRepository)
tag_repo = AsyncMock(spec=BranchTagRepository)
review_repo = AsyncMock(spec=BranchReviewRepository)

service = SummaryService(
    summary_repo=summary_repo,
    branch_tag_repo=tag_repo,
    review_repo=review_repo,
    sentiment_repo=AsyncMock(),
)
```

### 주요 테스트 시나리오

**감정 분석:**
- 긍정/부정/중립 기본 판정
- 이중부정 ("불편하지 않다" → 긍정)
- 양보/반전 구문 ("친절했지만 더러웠어요" → mixed)
- 짧은 리뷰 (< 30자) 판정
- 평점 + 텍스트 불일치 중재

**태그 분류:**
- 규칙 기반 정확 매칭
- 임베딩 기반 유사도 분류
- 범용 키워드 제외
- 충돌 해소 (pos+neg 공존)

**파이프라인:**
- 정상 9단계 처리
- 단계별 실패 격리 (Step 4 실패 → Step 7,8,9 스킵)
- 빈 리뷰 / 욕설 / 광고 필터링
- 대량 처리 (메모리 안정성)

**리포트:**
- 4단계 정상 생성
- AI 텍스트 숫자 할루시네이션 교정
- 캐시 히트/미스
- 리뷰 부족 시 처리

### 테스트 실행

```bash
# 전체 테스트
uv run pytest tests/ -v

# 감정 분석 테스트만
uv run pytest tests/test_sentiment_core.py -v

# 파이프라인 통합 테스트
uv run pytest tests/test_integration_pipeline.py -v

# 커버리지
uv run pytest tests/ --cov=app --cov-report=html
```

---

## 4.2 트러블슈팅

### 동기화가 실행되지 않음

| 확인 사항 | 진단 방법 | 해결 |
|-----------|-----------|------|
| Athena 설정 누락 | 로그: `Athena 클라이언트가 설정되지 않았습니다` | `.env`에 `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `ATHENA_DATABASE`, `ATHENA_OUTPUT_BUCKET` 설정 |
| DB 연결 실패 | 로그: `asyncpg` 관련 에러 | `DATABASE_URL` 확인, PostgreSQL 실행 상태 확인 |
| 이미 실행 중 | sync_metadata 잠금 | 이전 동기화가 완료될 때까지 대기 |

### AI 요약이 생성되지 않음

| 확인 사항 | 진단 방법 | 해결 |
|-----------|-----------|------|
| 리뷰 부족 | 응답: `{"success": false}` | 최소 30건 리뷰 필요 (전체 기간 포함) |
| API 키 누락 | 500 에러 + traceback | `.env`에 `OPENAI_API_KEY` 설정 |
| Rate Limit | 429 에러 | `OPENAI_RPM` 확인 (기본 3500) |
| LLM 할루시네이션 | 요약 내 잘못된 숫자 | `_fix_number_hallucinations()` 자동 교정 확인 |

### 태그 분류가 예상과 다름

| 증상 | 원인 | 확인 방법 |
|------|------|-----------|
| 항상 "기타" | 임베딩 유사도 < 0.50 | `/tag-tester` 페이지에서 키워드 테스트 |
| 잘못된 태그 매핑 | 규칙 역인덱스 오매칭 | `patterns.py` RULE_BASED_TAG_MAPPING 확인 |
| ABSA 미분류 | 절 분리 실패 | `ClauseChunker` 출력 확인 |
| 감정 반전 | 양보 구문 미감지 | `CONCESSION_REGEX` 패턴 확인 |

### 리포트 생성 실패

| 확인 사항 | 진단 방법 | 해결 |
|-----------|-----------|------|
| 태그 통계 없음 | Step 2 warning 로그 | 해당 지점 파이프라인 재실행 (동기화) |
| LLM 호출 실패 | Step 3 에러 로그 | API 키/네트워크 확인, fallback_summary 반환됨 |
| PDF 생성 실패 | `fpdf2` 에러 | 폰트 파일 존재 여부 확인 |
| 캐시 미갱신 | 리포트 내용 오래됨 | 새 리뷰 30건 이상이면 자동 재생성 (CLT 기준) |

### 대시보드 로딩 느림

| 확인 사항 | 진단 방법 | 해결 |
|-----------|-----------|------|
| 필터 옵션 캐시 만료 | TTLCache 300s | 5분 대기 후 자동 갱신 |
| Athena 쿼리 타임아웃 | 분석 페이지 500 에러 | Athena 실패 → Supabase 폴백 확인 |
| 대량 리뷰 조회 | 응답 지연 | 페이지네이션 limit 확인 |

### 로그 이벤트 참조

| 이벤트 | 레벨 | 의미 |
|--------|------|------|
| `[Startup] Database engine initialized` | INFO | DB 엔진 초기화 완료 |
| `[Startup] NLP models prewarmed` | INFO | Kiwi/HybridClassifier/Sentiment 로드 완료 |
| `sync_reviews started` | INFO | 동기화 시작 |
| `_process_day_chunk` | INFO | 일별 청크 처리 중 |
| `pipeline step failed` | WARNING | 파이프라인 단계 실패 (다음 단계 진행) |
| `analysis_failed` | ERROR | AI 분석 실패 (traceback 포함) |
| `llm_call_failed` | ERROR | OpenAI API 호출 실패 |
| `db_retry_attempt` | WARNING | DB 연결 재시도 |
| `ghost_reviews_cleaned` | INFO | 고스트 리뷰 정리 완료 |
| `report_generation_failed` | ERROR | 리포트 생성 실패 |
| `hallucination_fixed` | WARNING | 숫자 할루시네이션 자동 교정 |

---

## 4.3 용어 사전

| 용어 | 설명 |
|------|------|
| `branch_id` | 렌트카 지점 고유번호. 시스템 전체에서 지점을 식별하는 기본 키 |
| `review_id` | 리뷰 고유번호. Athena에서 발급 |
| ABSA | Aspect-Based Sentiment Analysis. 리뷰를 태그(aspect)별로 분리하여 각각의 감정을 분석하는 기법 |
| `tag_sentiments` | 리뷰 1건의 태그별 감정 분류 결과. `{태그명: {"positive": [...], "negative": [...], "neutral": [...]}}` |
| `branch_tags` | 지점별 태그 집계 테이블. 각 태그의 positive/negative/neutral 건수 저장 |
| CLT | Change List Threshold. 리포트 캐시 무효화 기준 (새 리뷰 30건 이상) |
| Athena | AWS Athena. Carmore의 리뷰 원본이 저장된 데이터 레이크 |
| Kiwi | 한국어 형태소 분석기. 키워드 추출에 사용 (C++ 기반, 스레드 안전 아님) |
| FastEmbed | ONNX 기반 경량 임베딩 모델. 태그 유사도 계산에 사용 |
| 규칙 역인덱스 | HybridClassifier 내부의 O(1) 키워드→태그 매핑 테이블 |
| 이중부정 | "불편하지 않다" 같은 표현. 부정어 + 부정어 = 긍정으로 처리 |
| 양보/반전 구문 | "~지만", "~는데" 등. 앞쪽 감정과 뒤쪽 감정이 반전되는 표현 |
| `ProcessedReviewDTO` | 파이프라인 처리 완료된 리뷰. 키워드, 감정, 태그 분류 결과 포함 |
| `PipelineResultDTO` | 파이프라인 전체 실행 결과. 단계별 성공/실패, 소요 시간 포함 |
| `ReportData` | 완성된 리포트 Pydantic 모델. PDF 생성 입력으로 사용 |
| Ghost review | Athena에 없지만 PostgreSQL에만 남아있는 리뷰. 정리 대상 |
| 오배정 | 하나의 branch_id에 여러 업체 리뷰가 섞인 상태. 80% 기준으로 소수 업체 제거 |
| Fallback | 주 경로 실패 시 대체 경로. 예: Athena 실패 → Supabase, Gemini 실패 → GPT |
| DI | Dependency Injection. FastAPI `Depends()`로 서비스에 Repository 주입 |
| RPC | Remote Procedure Call. Supabase PostgreSQL 함수 호출 (`getTagStatsByPeriod` 등) |
| TTLCache | Time-To-Live 캐시. 일정 시간 후 자동 만료 (필터 옵션: 300초) |
| Savepoint | PostgreSQL 중첩 트랜잭션. 파이프라인 단계별 롤백을 독립적으로 처리 |
