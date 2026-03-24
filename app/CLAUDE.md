# app/ — 프로젝트 아키텍처

## Architecture

```text
Request → API (endpoints) → Service → Domain/Repository → Response
                              ↓
                         Infrastructure (LLM)
```

## Tech Stack

- **Backend**: Python 3.12, FastAPI
- **NLP**: Kiwi (한국어 형태소 분석), FastEmbed (ONNX 기반)
- **LLM**: OpenAI GPT-4o-mini
- **Database**: PostgreSQL (SQLAlchemy Async + asyncpg)
- **Data**: pandas, openpyxl

## Directory Map

| Directory | Role |
| --------- | ---- |
| `main.py` | FastAPI 진입점, 앱 생성 |
| `api/v1/` | API 라우터, 엔드포인트 → `api/CLAUDE.md` |
| `domain/analysis/` | 감정 분석, ABSA, 태그 임베딩 → `domain/CLAUDE.md` |
| `domain/pipeline/` | 배치/증분 처리 파이프라인 |
| `infrastructure/llm/` | LLM 프로바이더 (OpenAI) |
| `services/` | 비즈니스 로직 레이어 |
| `repository/` | DB 접근 레이어 → `repository/CLAUDE.md` |
| `models/` | Pydantic DB 모델 |
| `schemas/` | API 요청/응답 DTO |
| `scripts/` | 운영 스크립트 → `scripts/CLAUDE.md` |
| `templates/` | HTML 대시보드 → `templates/CLAUDE.md` |
| `static/` | CSS, JS 정적 파일 |
| `core/` | 설정, 의존성 |
| `data/` | 데이터 파일 |

## Code Principles

1. **단일 책임**: 하나의 파일/함수는 하나의 역할
2. **의존성 주입**: `core/deps.py`에서 서비스 생성
3. **Repository 패턴**: Repository로 DB 접근 추상화
4. **DTO 패턴**: 데이터 전송 객체로 타입 안전성 보장
5. **순환 참조 방지**: 함수 내부 import 사용
6. **에러 처리**: HTTPException으로 적절한 에러 응답
7. **로깅**: logging 모듈로 에러 상황 기록

## Environment Variables

`.env` 필수: `OPENAI_API_KEY`, `LLM_PROVIDER`, `DATABASE_URL`, `API_PREFIX`

- `DATABASE_URL`: `postgresql+asyncpg://user:pass@host:port/dbname`
- 로컬: `API_PREFIX=/api` / 서버: `API_PREFIX=/review/api`

## Architecture Decisions

- 데이터 정합성: DB 레벨 솔루션(트리거, 제약조건, 계산 컬럼) 우선
- 명시적 요청 없이 API 측 데이터 수정 금지
