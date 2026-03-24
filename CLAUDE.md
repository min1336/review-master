# Review Summary AI

Carmore 렌트카 리뷰 요약 시스템 - 운영팀 모니터링 대시보드

---

## Conventions — 핵심 규칙

### Working Style

- 변경 요청을 받으면 즉시 코딩을 시작할 것. 광범위한 확인 질문을 하지 말고 합리적인 가정을 하여 진행할 것
- 정말 모호한 경우에만 최대 1개의 핵심 질문만 할 것
- 명시적으로 요청된 변경만 수행할 것. 추가 개선, 리팩터링, 스타일 변경을 임의로 하지 말 것
- UI 조정 시 언급된 특정 속성만 변경할 것

### Coding Standards

- Use FastAPI typed routes with Pydantic models
- Error handling: try-except with proper status codes
- Database: Use transaction context managers
- Prefer explicit function names over one-liners
- Type hints required for all functions
- Avoid nested conditionals in business logic

### Git Rules

- push/PR은 사용자 허가 필수
- main/master 직접 푸시 금지 → feature 브랜치 + PR
- Rebase Merge: `git checkout target && git rebase source`
- 커밋 메시지: `FEAT:(AI-N) 내용` 또는 `FIX:(AI-N) 내용`
- Git Worktree: `.worktrees/` 디렉토리 사용

### Testing

- 버그 수정 시 대상 + 인접 카테고리 모두 기존 테스트 실행하여 회귀 확인
- 수정 → 전체 테스트 → 통과 확인 순서 필수

---

## Documentation Map — 문서 라우팅

| 주제 | 문서 위치 |
| ---- | --------- |
| 아키텍처, 기술 스택, 디렉토리 구조, 환경변수, 코드 원칙 | `app/CLAUDE.md` |
| API 규칙, 라우트 순서, 비동기 패턴, 엔드포인트 | `app/api/CLAUDE.md` |
| 태그 시스템, 감정 분석, 도메인 상수 | `app/domain/CLAUDE.md` |
| DB 규칙, 트랜잭션, 마이그레이션, branch_tags | `app/repository/CLAUDE.md` |
| 프론트엔드 규칙, XSS 방어, CSS/JS, 대시보드 | `app/templates/CLAUDE.md` |
| 개발 명령어, 운영 스크립트 | `app/scripts/CLAUDE.md` |
| API 엔드포인트 전체 목록, DB 테이블 요약, UI 패턴 | `.claude/docs/reference.md` |
| DB 스키마 상세 (27개 테이블 컬럼, 관계도, 데이터 흐름) | `.claude/docs/database-schema.md` |
