# app/api/ — API 레이어

## Conventions

- 라우트 순서: 고정 경로(`/list`, `/batch`) → path parameter(`/{id}`)
- FastAPI typed routes with Pydantic models
- Error handling: try-except with HTTPException + 적절한 status code
- API Envelope: `{"success": true, "data": ..., "count": N}`

## Route Registration

라우트 목록은 `v1/api.py`에서 sub-router 패턴으로 등록.

## 비동기 작업 패턴

긴 작업(60초+)은 백그라운드 + 폴링:

```text
POST .../async → job_id
GET  .../job/{id} → status + progress (2초 간격 폴링)
```

- 최대 60회 폴링
- `AbortController`로 모달 닫기 시 폴링 취소
- 프론트엔드: `updateReportProgress()` 패턴

## Endpoint Reference

> 전체 엔드포인트 목록 (Method, Path, Description) → `.claude/docs/reference.md` 참조

### 주요 라우트 그룹

| Prefix | 역할 |
| ------ | ---- |
| `/api/v2/summaries` | 요약 CRUD |
| `/api/tags` | 태그 관리 |
| `/api/sentiment` | 감정 통계 |
| `/api/analysis` | 필터링 분석 |
| `/api/v2/report` | 리포트 생성/조회 |
| `/`, `/analysis`, `/tag-tester` | 페이지 라우트 |
