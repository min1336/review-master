# Review Summary AI

Carmore 렌트카 리뷰 AI 요약 시스템

## Overview

렌트카 고객 리뷰를 자동으로 분석하여 지점별 요약을 생성하는 시스템입니다.

**주요 기능:**
- 리뷰 키워드 자동 추출 (MeCab 형태소 분석)
- 태그+감정 분류 (규칙 기반 ABSA)
- AI 요약 생성 (OpenAI GPT-4o-mini)
- 운영팀 모니터링 대시보드

## Tech Stack

| Category | Technology |
|----------|------------|
| Backend | Python 3.10+, FastAPI |
| NLP | MeCab, Sentence-Transformers |
| LLM | OpenAI GPT-4o-mini |
| Database | Supabase (PostgreSQL) |
| Frontend | Jinja2, HTML/CSS/JS |
| Package Manager | uv |

## Quick Start

### 1. 환경 설정

```bash
# uv 설치 (없는 경우)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 의존성 설치
uv sync
```

### 2. 환경변수 설정

`.env` 파일 생성:
```env
OPENAI_API_KEY=sk-...
LLM_PROVIDER=openai
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...
```

### 3. 실행

```bash
cd app
python main.py
```

접속: http://localhost:8000

## Project Structure

```
app/
├── main.py              # FastAPI 진입점
├── api/v1/              # API 엔드포인트
│   └── endpoints/       # summaries, tags, sentiment
├── domain/              # 도메인 로직
│   ├── analysis/        # 분석 모듈
│   └── pipeline/        # 파이프라인
├── infrastructure/      # 외부 연동
│   └── llm/             # OpenAI 프로바이더
├── services/            # 비즈니스 로직
├── crud/                # Repository 레이어
├── models/              # DB 모델
├── schemas/             # API 스키마
├── core/                # 설정
└── templates/           # HTML 템플릿
```

## API

### 요약 API
```
GET  /api/v2/summaries              # 요약 목록
GET  /api/v2/summaries/{id}         # 요약 상세
GET  /api/v2/summaries/{id}/detail  # 지점 상세 분석
PUT  /api/v2/summaries/{id}         # 요약 수정
POST /api/v2/summaries/{id}/regenerate  # AI 재생성
```

### 태그 API
```
GET  /api/tags/list           # 태그 목록
GET  /api/tags/groups         # 그룹별 태그
GET  /api/tags/{id}           # 태그 상세
GET  /api/tags/batch          # 일괄 조회
GET  /api/tags/branch/{id}    # 지점별 태그
```

### 감정 API
```
GET  /api/sentiment/stats           # 감정 통계
GET  /api/sentiment/branch/{id}     # 지점별 감정
```

API 문서: http://localhost:8000/docs

## Features

### 키워드 추출
- MeCab 형태소 분석 기반
- 불용어 필터링
- 가중치 계산 (TF-IDF 유사)

### 감정 분석
- 규칙 기반 패턴 매칭
- 이중부정 처리 (`불편함이 없다` → 긍정)
- 문맥 윈도우 분석 (앞뒤 20자)

### 태그 분류
- 7개 기본 태그: 고객응대, 차량상태, 가성비, 반납/픽업, 위치/접근성, 서비스, 보험/보장
- 임베딩 기반 유사도 분류
- 커스텀 태그 지원

## Development

```bash
# 개발 의존성 설치
uv sync --group dev

# 린트
uv run ruff check app/

# 테스트
uv run pytest
```

## License

Private - Carmore Internal Use Only
