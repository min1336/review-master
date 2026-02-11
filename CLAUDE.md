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
│   ├── summary_service.py         # 요약 + 상세분석
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
│   ├── migrate_sentiments.py      # 마이그레이션
│   └── run_auto_mapping.py        # 키워드 자동 매핑 (52개 태그)
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
| POST | `/analyze-tags` | 태그 분석 테스트 |
| GET | `/categories` | 카테고리 목록 |
| POST | `/categories` | 카테고리 생성 |
| GET | `/list` | 태그 목록 (페이지네이션) |
| POST | `/batch` | 지점별 태그 일괄 조회 |
| POST | `/` | 태그 생성 |
| PUT | `/{id}` | 태그 수정 |
| DELETE | `/{id}` | 태그 삭제 |

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

### 카테고리 7개 (문장형)
직원이 친절함, 사고 처리를 잘해줌, 주유비 부담 없음, 가격이 저렴함, 차량이 청결함, 차량외관이 좋음, 배달 서비스가 우수함

### 세분화 태그 52개
각 카테고리 하위에 세분화 태그 매핑 (`patterns.py` RULE_BASED_TAG_MAPPING)
- 예: "직원이 친절함" → 친절, 안내, 설명, 서비스, 고객응대, 응대속도, 전화응대, 예약

### API 응답 Envelope 패턴
태그 API는 `{"success": true, "data": ..., "count": N}` 형식 사용

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

## Testing

- 버그 수정 시 (특히 감정/분류 로직) 대상 수정과 인접 카테고리 모두에 대해 기존 테스트 케이스를 실행하여 회귀를 확인한 후 완료 선언할 것
- 수정 → 전체 테스트 → 통과 확인 순서를 반드시 지킬 것

## Architecture Decisions

- 데이터 정합성 문제는 애플리케이션 레벨 오버라이드보다 DB 레벨 솔루션(트리거, 제약조건, 계산 컬럼)을 우선할 것
- 명시적으로 요청받지 않은 한 API 측 데이터 수정을 시도하지 말 것

## Git Rules

- **push/PR은 사용자 허가 필수**: git push, PR 생성 전 반드시 사용자에게 확인받을 것
- **main/master 브랜치에 직접 푸시 금지**: 절대로 root 브랜치(main, master)에 직접 push하지 말 것. 반드시 feature 브랜치에서 작업 후 PR을 통해 병합할 것.
- **Rebase Merge 사용**: PR 병합 시 merge commit 대신 rebase merge 사용
- **브랜치 병합 명령어**: `git checkout target && git rebase source` (일반 merge 금지)
- **커밋 메시지 규칙**: `FEAT:(AI-티켓번호) 내용` 또는 `FIX:(AI-티켓번호) 내용` 형식
- **Git Worktree**: `.worktrees/` 디렉토리 사용 (gitignore에 추가됨)
- **Worktree 정리**: `git worktree remove <path> --force && git branch -D <branch>`
- **브랜치 일괄 삭제**: `git branch | grep -v "main" | xargs git branch -D`

## Database Tables

| 테이블 | 용도 |
|--------|------|
| `branch_summaries` | 지점별 요약 데이터 |
| `branch_reviews` | 원본 리뷰 데이터 |
| `branch_tags` | 지점별 태그 매핑 |
| `tags` | 태그 마스터 (52개) |
| `tag_categories` | 태그 카테고리 (7개) |
| `keyword_mappings` | 키워드 → 태그 매핑 |
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

### 프론트엔드 폴링 구현
- `AbortController`로 모달 닫기 시 폴링 취소
- 최대 폴링 횟수 설정 (60회 = 2분 타임아웃)
- 진행률 UI: `updateReportProgress(progress, status)` 패턴

## 프론트엔드 수정 시 주의사항

- **innerHTML 대신 DOM API 사용**: 보안 훅이 innerHTML에 XSS 경고 발생
  - `document.createElement()` + `container.replaceChildren()` 패턴 권장
- **escapeHtml 함수 사용**: `dashboard_v2.html:1669`에 정의됨 - 사용자 데이터를 innerHTML에 삽입 시 필수
- **let 변수 스코프**: 호이스팅 안 됨 - 사용하는 함수보다 위에 선언
- **regenerate vs generate**: `regenerate_report()`는 내부적으로 `generate_report()` 호출 (동일 로직)

## 대시보드 UI 패턴

### 지역 변환 함수
`toMetroRegion()` - 상세 지역(전남 여수시)을 광역 단위(전라남도)로 변환
- 위치: `dashboard_v2.html` 내 JavaScript
- 17개 광역시/도 매핑 (서울, 부산, 대구, 인천, 광주, 대전, 울산, 세종, 경기, 강원, 충북, 충남, 전북, 전남, 경북, 경남, 제주)

### 즐겨찾기 페이지네이션
- `localStorage`에 `dashboard_favorites` 키로 branch_id 배열 저장
- 페이지당 고정 개수 유지 (DEFAULT_PAGE_SIZE: 30)
- 즐겨찾기가 페이지 넘치면 다음 페이지로 이동
- offset 계산: `prevNormalShown = Math.max(0, (currentPage * pageSize) - favCount)`

## FastAPI 라우트 주의사항

- **라우트 순서**: 고정 경로(`/list`, `/batch`) → path parameter 경로(`/{id}`) 순서 배치 (FastAPI가 위→아래 순서로 매칭)

## 개발 명령어

- `python -m py_compile <file.py>` - Python 문법 검사
- Supabase MCP로 마이그레이션: `mcp__supabase__apply_migration`
- `python app/scripts/run_auto_mapping.py` - 키워드 자동 매핑 (52개 태그 기반)

## Claude Code 도구 레퍼런스

### 슬래시 커맨드 (Skill tool)

| 커맨드 | 용도 |
|--------|------|
| `/code-review` | PR 코드 리뷰 |
| `/feature-dev` | 가이드 기반 기능 개발 (코드베이스 이해 + 아키텍처) |
| `/review-pr` | 종합 PR 리뷰 (전문 에이전트 활용) |
| `/revise-claude-md` | 세션 학습으로 CLAUDE.md 업데이트 |
| `/claude-md-improver` | CLAUDE.md 감사/개선 |
| `/frontend-design` | 프론트엔드 인터페이스 생성 |
| `/claude-automation-recommender` | Claude Code 자동화 추천 |
| `/ralph-loop` | Ralph Loop 시작 |
| `/cancel-ralph` | Ralph Loop 취소 |
| `/hookify` | 훅 규칙 생성 |
| `/writing-plans` | 구현 계획 작성 |
| `/executing-plans` | 구현 계획 실행 |
| `/brainstorming` | 구현 전 브레인스토밍 |
| `/systematic-debugging` | 체계적 디버깅 |
| `/test-driven-development` | TDD 기반 개발 |
| `/verification-before-completion` | 완료 전 검증 |
| `/requesting-code-review` | 코드 리뷰 요청 |
| `/receiving-code-review` | 코드 리뷰 피드백 처리 |
| `/finishing-a-development-branch` | 개발 브랜치 마무리 (merge/PR/cleanup) |
| `/using-git-worktrees` | Git worktree 격리 작업 |
| `/dispatching-parallel-agents` | 병렬 에이전트 디스패치 |
| `/subagent-driven-development` | 서브에이전트 기반 구현 |

### MCP 서버

| 서버 | 주요 기능 | 사용 시점 |
|------|----------|----------|
| **Supabase** | DB 테이블 조회, SQL 실행, 마이그레이션, Edge Functions, 타입 생성 | DB 스키마 변경, 데이터 조회, Edge Function 배포 |
| **Context7** | 라이브러리 문서/코드 예제 검색 | 외부 라이브러리 사용법 확인 시 |
| **Playwright** | 브라우저 자동화 (스크린샷, 클릭, 폼 입력, DOM 스냅샷) | 프론트엔드 테스트, UI 확인 |

### Task 에이전트 (Task tool)

| 에이전트 | 용도 | 사용 시점 |
|---------|------|----------|
| `Explore` | 코드베이스 탐색 | 파일/패턴 검색, 아키텍처 이해 |
| `Plan` | 구현 설계 | 구현 전략 수립 |
| `feature-dev:code-reviewer` | 버그, 보안, 품질 리뷰 | 코드 작성 후 |
| `feature-dev:code-explorer` | 실행 경로/아키텍처 분석 | 기존 코드 깊이 이해 |
| `feature-dev:code-architect` | 기능 아키텍처 설계 | 새 기능 설계 시 |
| `pr-review-toolkit:code-reviewer` | PR 코드 리뷰 | PR 생성 전 |
| `pr-review-toolkit:silent-failure-hunter` | 사일런트 실패 탐지 | 에러 핸들링 리뷰 |
| `pr-review-toolkit:type-design-analyzer` | 타입 설계 분석 | 새 타입 도입 시 |
| `pr-review-toolkit:comment-analyzer` | 코멘트 정확성 분석 | 문서 주석 추가 후 |
| `pr-review-toolkit:pr-test-analyzer` | 테스트 커버리지 분석 | PR 테스트 검증 |
| `episodic-memory` | 세션 간 기억 검색 | 이전 세션 결정/해결책 복원 |
| `claude-code-guide` | Claude Code 사용 가이드 | Claude Code 기능 질문 |
