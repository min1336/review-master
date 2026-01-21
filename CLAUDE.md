# Review Summary AI

AI-powered review summarization system for Carmore car rental company.

## Tech Stack

- **Backend**: Python 3.x, Flask
- **NLP**: MeCab (Korean morphology), Sentence-Transformers (embedding)
- **LLM**: OpenAI GPT-4o-mini
- **Database**: Supabase (PostgreSQL)
- **Data**: pandas, openpyxl

## Key Constants

```python
MIN_REVIEWS_PER_BRANCH = 30
MIN_REVIEW_LENGTH = 5
OPENAI_RPM = 3500
MAX_REVIEWS_PER_BRANCH = 30  # recent_reviews 테이블 저장 개수
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
SIMILARITY_THRESHOLD = 0.3  # 태그 분류 최소 유사도
```

## Directory Structure

```
src/
├── analysis/           # Sentiment & keyword modules
│   ├── sentiment/      # Lexicon, BERT, Hybrid analyzers
│   ├── keywords/       # MeCab extraction, weighting
│   ├── chunking/       # Clause-level text chunking
│   └── tags/           # Tag mapping & embedding classifier
├── config/             # Settings, stopwords
├── llm/                # OpenAI provider
├── pipeline/           # Batch processing orchestration
├── db/                 # Database connectivity
└── preprocessing/      # Data cleaning

scripts/                # Pipeline execution scripts
web/                    # Flask API + dashboard
data/                   # Input Excel files
output/                 # Generated results
```

## Common Commands

```bash
# Run full pipeline
python -c "from src.pipeline import BatchPipeline; BatchPipeline().run('data/리뷰리스트_매핑완료_20260109.xlsx')"

# Run incremental update
python scripts/pipeline_incremental.py

# Single branch detailed analysis (Excel export)
python scripts/export_branch_detail.py --branch_id 2

# Start web dashboard
python web/app.py

# Test LLM provider
python -c "from src.llm import get_provider; p = get_provider(); print(p.model_name)"
```

## Single Branch Analysis

`scripts/export_branch_detail.py` - 단일 업체 상세 분석 엑셀 생성

```bash
python scripts/export_branch_detail.py --branch_id 2 --input data/리뷰리스트_매핑완료_20260109.xlsx
```

**출력 구조**:
- 상단: 업체명 / 위치 / 리뷰수 / 태그목록 / 1개월~전체 요약 (5개 기간)
- 하단: 모든 리뷰 + 리뷰별 추출 키워드 + 태그별 감정 (예: `고객응대(+), 차량상태(-)`)

**처리 흐름**:
1. 데이터 로드 → 지점 필터링
2. 키워드 추출 (MeCab)
3. 리뷰별 태그+감정 분류 → 지점 집계
4. 기간별 AI 요약 생성
5. 엑셀 출력 (`output/{업체명}_상세분석_{timestamp}.xlsx`)

## Pipeline Overview (v5.0)

> 감정분석 제거, 키워드별 감정 판단으로 대체 (6배 속도 향상)

1. **Step 1**: Load Excel (88K reviews - 매핑 완료 파일)
2. **Step 2**: Keyword extraction (청킹 + MeCab)
3. **Step 3**: Tag+Sentiment classification + Aggregate + LLM summarization
4. **Step 4**: Export (Supabase)

### 파이프라인 옵션
```python
pipeline = BatchPipeline(
    use_chunking=True,        # 절 단위 청킹 (접속사/연결어미 기준)
    use_embedding_tags=True   # 임베딩 기반 태그+감정 분류
)
```

### 감정 판단 방식
- 리뷰별 감정분석 → **키워드별 규칙 패턴 매칭 + 문맥 분석**
- 부정 패턴: `불친절`, `비싸`, `냄새`, `아쉬운`, `최악`, `쩔어` 등 (100+개)
- 이중부정 처리: `불편함이 없다`, `불만 없다` → 긍정으로 분류
- 긍정예외 처리: `편안하다`, `생각하지 못한 세심한` → 부정 패턴 무시
- 문맥 윈도우: 키워드 앞뒤 20자 범위에서 감정 패턴 탐지

### 태그 분류 방식
- **규칙 기반 매핑**: 도메인 키워드 → 태그 (브레이크→차량상태, 친절→고객응대)
- **임베딩 기반 분류**: Sentence-Transformers 코사인 유사도 (threshold: 0.3)
- **태그 목록**: 고객응대, 차량상태, 가성비, 반납/픽업, 위치/접근성, 서비스, 보험/보장

## Environment Variables

Required in `.env`:
- `OPENAI_API_KEY` - GPT API key
- `LLM_PROVIDER` - "openai"
- `SUPABASE_URL` - Database URL
- `SUPABASE_KEY` - Service role key

## Status Workflow

Summaries follow: `draft` -> `approved` -> `published`

| DB 값 | 표시 라벨 |
|-------|----------|
| draft | 보류 |
| approved | 승인 |
| published | 게시 |

## Dashboard 태그 시스템

### 데이터 소스
- **자동 생성**: `branch_tags` 테이블 (파이프라인에서 생성)
- **수동 편집**: `branch_summaries.keywords` 배열

### 태그 로드 우선순위
```
1. keywords 배열 (수동 선택)
2. keyword_1,2,3 (레거시)
3. branch_tags top3 (자동 fallback)
```

### 기본 태그 7개
고객응대, 차량상태, 가성비, 반납/픽업, 위치/접근성, 서비스, 보험/보장

### 태그 기능
- 클릭으로 선택/해제
- 선택 안해도 됨 (0개 가능)
- 커스텀 태그 추가/삭제 가능
- `keywords` 배열로 저장 (개수 제한 없음)

### 통합 수정 모드
하단 "수정" 버튼 클릭 시:
- 지역 (region)
- 태그 (keywords)
- 요약 (summary_all, summary_1y, summary_6m, summary_3m, summary_1m)

동시 편집 후 "저장" 버튼으로 일괄 저장

## Dashboard API

```bash
# 요약 수정 (지역, 태그, 요약 일괄)
PUT /api/v2/summaries/{branch_id}
{
  "region": "서울 강남구",
  "keywords": ["고객응대", "차량상태"],
  "summary_all": "..."
}

# 태그 일괄 조회 (최적화됨)
GET /api/tags/batch?branch_ids=1,2,3
```

## Planning with Files Pattern

복잡한 작업 시 컨텍스트 유지를 위한 3-파일 패턴:

| File | Purpose |
|------|---------|
| `docs/task_plan.md` | 작업 계획 & 체크리스트 (결정 전 검토) |
| `docs/findings.md` | 연구 결과 & 코드 분석 저장 |
| `docs/progress.md` | 시도 & 실패 기록 (실수 반복 방지) |

**사용 시점**: 다단계 작업, 리팩토링, 연구 작업
**건너뛸 때**: 단순 쿼리, 빠른 수정

## Code Principles

모든 코드와 파일은 **유지/보수/확장/수정이 용이**하게 작성:

```
1. 단일 책임 원칙 (SRP)
   - 하나의 파일/함수는 하나의 역할만
   - 변경 이유가 하나만 있도록

2. 명확한 네이밍
   - 파일: snake_case (예: batch_pipeline.py)
   - 클래스: PascalCase (예: BatchPipeline)
   - 함수/변수: snake_case (예: analyze_sentiment)

3. 문서화
   - 모든 모듈: 상단에 목적 설명
   - 복잡한 함수: docstring 필수
   - 매직 넘버 금지: 상수로 정의

4. 의존성 관리
   - 순환 참조 금지
   - 의존성 주입 패턴 사용
   - 설정은 .env 또는 config/에서 관리

5. 확장성
   - 하드코딩 금지
   - 인터페이스/추상 클래스 활용
   - 새 기능 추가 시 기존 코드 수정 최소화
```
