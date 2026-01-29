# Review Summary AI

Carmore 렌트카 리뷰 요약 시스템 - 운영팀 모니터링 대시보드

## Overview

렌트카 서비스 리뷰를 자동으로 분석하고 요약하는 AI 기반 대시보드 시스템입니다.

### 주요 기능

- **리뷰 분석**: 한국어 형태소 분석(Kiwi)을 통한 키워드 추출
- **감정 분석**: 규칙 기반 + 하이브리드 분류로 긍정/부정/중립 판단
- **태그 분류**: 7개 카테고리(친절도, 사고, 주유, 가격, 청결, 차량상태, 딜리버리)
- **AI 요약**: GPT-4o-mini를 활용한 지점별 요약 생성
- **대시보드**: 운영팀용 모니터링 및 관리 인터페이스

## Tech Stack

| Category | Technology |
|----------|------------|
| Backend | Python 3.12, FastAPI |
| NLP | Kiwi, Sentence-Transformers |
| LLM | OpenAI GPT-4o-mini |
| Database | Supabase (PostgreSQL) |
| Frontend | HTML, JavaScript (Vanilla) |

## Installation

### 1. 저장소 클론

```bash
git clone https://github.com/your-org/Review_Summary_AI.git
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
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...
API_PREFIX=/api
```

### 4. 실행

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Pages

| URL | Description |
|-----|-------------|
| `/` | 메인 대시보드 - 지점 요약 목록, 통계 |
| `/analysis` | 리뷰 분석 - 필터링 및 검색 |
| `/tag-tester` | 태그 테스트 - 리뷰 텍스트 분석 테스트 |

## API Documentation

서버 실행 후 `/docs`에서 Swagger UI 확인 가능

### 주요 API

```
GET  /api/v2/summaries          # 요약 목록
GET  /api/v2/summaries/{id}     # 요약 상세
GET  /api/analysis/filters      # 필터 옵션
GET  /api/analysis/reviews      # 필터링된 리뷰
GET  /api/sentiment/stats       # 감정 통계
GET  /api/tags/list             # 태그 목록
```

## Project Structure

```
app/
├── api/v1/endpoints/    # API 엔드포인트
├── services/            # 비즈니스 로직
├── repository/          # DB 접근 레이어
├── domain/              # 핵심 도메인 로직
│   ├── analysis/        # NLP 분석 모듈
│   └── pipeline/        # 데이터 처리 파이프라인
├── infrastructure/      # 외부 시스템 (LLM)
├── models/              # DB 모델
├── schemas/             # DTO
└── templates/           # HTML 템플릿
```

## Docker

```bash
# 빌드
docker build -t review-summary-ai .

# 실행
docker-compose -f docker-compose.prod.yml up -d
```

## License

Private - Carmore Internal Use Only
