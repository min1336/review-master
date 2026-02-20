# CLAUDE.md - Rental Car Review API Standards
- Use FastAPI typed routes with Pydantic models
- Error handling: try-except with proper status codes
- Database: Use transaction context managers
- Prefer explicit function names over one-liners
- Type hints required for all functions
- Avoid nested conditionals in business logic

## Working Style

- 변경 요청을 받으면 즉시 코딩을 시작할 것. 광범위한 확인 질문을 하지 말고 합리적인 가정을 하여 진행할 것
- 정말 모호한 경우에만 최대 1개의 핵심 질문만 할 것

## Code Changes

- 명시적으로 요청된 변경만 수행할 것. 추가 개선, 리팩터링, 스타일 변경을 임의로 하지 말 것
- UI 조정 시 언급된 특정 속성만 변경할 것

# Review Summary AI

Carmore 렌트카 리뷰 요약 시스템 - 운영팀 모니터링 대시보드

## Tech Stack

- **Backend**: Python 3.12, FastAPI
- **NLP**: Kiwi (한국어 형태소 분석), FastEmbed (ONNX 기반)
- **LLM**: OpenAI GPT-4o-mini
- **Database**: Supabase (PostgreSQL)
- **Data**: pandas, openpyxl

> **SQL 마이그레이션 규칙**: SQL 마이그레이션 생성 시 유효한 SQL만 출력할 것. 마크다운 주석, 'Step N' 어노테이션, 비-SQL 텍스트를 포함하지 말 것

## Key Constants

```python
OPENAI_RPM = 3500                # API Rate Limit
EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
SIMILARITY_THRESHOLD = 0.3       # 태그 분류 최소 유사도
```

## Project Structure

- `app/main.py` — FastAPI 진입점
- `app/api/v1/` — API 라우터 및 엔드포인트 (라우트 목록: `app/api/v1/api.py`)
- `app/domain/analysis/` — 감정 분석, ABSA, 태그 임베딩
- `app/domain/pipeline/` — 배치/증분 처리 파이프라인
- `app/infrastructure/llm/` — LLM 프로바이더 (OpenAI)
- `app/services/` — 비즈니스 로직 레이어
- `app/repository/` — DB 접근 레이어 (테이블 구조는 각 Repository 파일 참조)
- `app/models/` — Pydantic DB 모델
- `app/schemas/` — API 요청/응답 DTO
- `app/templates/` — HTML 대시보드 (dashboard_v2, analysis, tag_tester)
- `app/static/js/shared-utils.js` — 공통 JS (escapeHtml, escapeAttr, showToast, apiRequest 등)
- `app/static/css/shared-theme.css` — 공통 CSS 변수, 리셋, toast 애니메이션

## Architecture

```
Request → API (endpoints) → Service → Domain/Repository → Response
                              ↓
                         Infrastructure (LLM)
```

## Code Principles

1. **단일 책임**: 하나의 파일/함수는 하나의 역할
2. **의존성 주입**: `deps.py`에서 서비스 생성
3. **Repository 패턴**: Repository로 DB 접근 추상화
4. **DTO 패턴**: 데이터 전송 객체로 타입 안전성 보장
5. **순환 참조 방지**: 함수 내부 import 사용
6. **에러 처리**: HTTPException으로 적절한 에러 응답
7. **로깅**: logging 모듈로 에러 상황 기록

## Environment Variables

`.env` 필수: `OPENAI_API_KEY`, `LLM_PROVIDER`, `SUPABASE_URL`, `SUPABASE_KEY`, `API_PREFIX`
- 로컬: `API_PREFIX=/api` / 서버: `API_PREFIX=/review/api`

## 태그 시스템

- 7개 카테고리, 52개 세분화 태그 (상세: `app/domain/analysis/patterns.py` RULE_BASED_TAG_MAPPING)
- 감정 판단: 규칙 패턴 매칭 + 문맥 분석, 이중부정 처리, 문맥 윈도우 20자
- API Envelope: `{"success": true, "data": ..., "count": N}`

## Testing

- 버그 수정 시 대상 + 인접 카테고리 모두 기존 테스트 실행하여 회귀 확인
- 수정 → 전체 테스트 → 통과 확인 순서 필수

## Architecture Decisions

- 데이터 정합성: DB 레벨 솔루션(트리거, 제약조건, 계산 컬럼) 우선
- 명시적 요청 없이 API 측 데이터 수정 금지

## Git Rules

- push/PR은 사용자 허가 필수
- main/master 직접 푸시 금지 → feature 브랜치 + PR
- Rebase Merge: `git checkout target && git rebase source`
- 커밋 메시지: `FEAT:(AI-N) 내용` 또는 `FIX:(AI-N) 내용`
- Git Worktree: `.worktrees/` 디렉토리 사용

## FastAPI 주의사항

- 라우트 순서: 고정 경로(`/list`, `/batch`) → path parameter(`/{id}`)

## 프론트엔드 주의사항

- innerHTML 대신 DOM API 사용 (보안 훅이 XSS 경고 발생)
- `escapeHtml` 사용 필수 (정의: `app/static/js/shared-utils.js`)
- HTML 속성(onclick, data-*, value)에는 `escapeAttr()` 사용 (같은 파일)
- 동적 텍스트 업데이트는 `innerHTML` 대신 `.textContent` 사용
- 모든 템플릿은 `shared-theme.css` + `shared-utils.js`를 `{{ base_path }}`로 참조
- CSS 변수: `shared-theme.css`에 superset 정의, 각 페이지는 로컬 오버라이드만 유지
- let 변수: 사용 함수보다 위에 선언
- `regenerate_report()`는 내부적으로 `generate_report()` 호출 (동일 로직)

## 비동기 작업 패턴

긴 작업(60초+)은 백그라운드 + 폴링: `POST .../async → job_id` + `GET .../job/{id}` (2초 간격)
- `AbortController`로 모달 닫기 시 폴링 취소, 최대 60회 폴링, `updateReportProgress()` 패턴

## 개발 명령어

- `python -m py_compile <file.py>` — 문법 검사
- `mcp__supabase__apply_migration` — Supabase 마이그레이션
- `python app/scripts/run_auto_mapping.py` — 키워드 자동 매핑

> 상세 API 엔드포인트, DB 테이블, 대시보드 UI 패턴 → `.claude/docs/reference.md` 참조
