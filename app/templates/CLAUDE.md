# app/templates/ — 프론트엔드 (HTML 대시보드)

## Security Rules

- `innerHTML` 대신 DOM API 사용 (보안 훅이 XSS 경고 발생)
- 동적 텍스트 업데이트는 `.textContent` 사용
- `escapeHtml()` 사용 필수 — 정의: `../static/js/shared-utils.js`
- HTML 속성(onclick, data-*, value)에는 `escapeAttr()` 사용 — 같은 파일

## Asset References

- 모든 템플릿은 `shared-theme.css` + `shared-utils.js`를 `{{ base_path }}`로 참조
- CSS 변수: `shared-theme.css`에 superset 정의, 각 페이지는 로컬 오버라이드만 유지

## Coding Rules

- let 변수: 사용 함수보다 위에 선언
- `regenerate_report()`는 내부적으로 `generate_report()` 호출 (동일 로직)

## Shared Utilities (`../static/js/shared-utils.js`)

| Function | 용도 |
| -------- | ---- |
| `escapeHtml()` | HTML 특수문자 이스케이프 |
| `escapeAttr()` | HTML 속성값 이스케이프 |
| `showToast()` | 토스트 알림 표시 |
| `apiRequest()` | API 호출 래퍼 |

## 비동기 작업 UI 패턴

- `AbortController`로 모달 닫기 시 폴링 취소
- 최대 60회 폴링 (2초 간격)
- `updateReportProgress()` 패턴으로 진행률 표시

## Dashboard Pages

| Template | 역할 |
| -------- | ---- |
| `dashboard_v2.html` | 메인 대시보드 (`/`) |
| `analysis.html` | 리뷰 분석 페이지 (`/analysis`) |
| `tag_tester.html` | 태그 테스트 페이지 (`/tag-tester`) |

## UI 패턴 Reference

> 지역 변환, 즐겨찾기, 페이지네이션 상세 → `.claude/docs/reference.md` 참조
