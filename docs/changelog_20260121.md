# 변경사항 - 2026.01.21

## 1. 서버 속도 최적화
- `/api/tags/batch` 엔드포인트 N+1 쿼리 문제 해결
- 378개 개별 쿼리 → 2개 쿼리로 최적화 (Supabase `in_()` 사용)

## 2. 상태 라벨 변경
| 기존 | 변경 |
|------|------|
| draft | 보류 |
| approved | 승인 |
| published | 게시 |

## 3. 기간 탭 UI 변경
- 전체/1년/6개월/3개월/1개월 탭 디자인 변경
- 회색 미니멀 스타일 (pill 버튼)
- 비활성: 연한 회색 배경, 활성: 진한 회색 배경 + 흰색 텍스트

## 4. 태그 시스템 전면 개편

### 4.1 UI 변경
- 텍스트 입력 방식 → 클릭 기반 선택/해제
- 7개 기본 태그: 고객응대, 차량상태, 가성비, 반납/픽업, 위치/접근성, 서비스, 보험/보장

### 4.2 기능
- 태그 선택/해제 (클릭)
- 선택 안해도 됨 (0개 가능)
- 커스텀 태그 추가 (입력 + 추가 버튼)
- 커스텀 태그 삭제 (✕ 버튼)

### 4.3 데이터 저장
- `branch_summaries.keywords` 배열로 저장
- 개수 제한 없음

### 4.4 Fallback 로직
```
1. keywords 배열 있으면 → 수동 선택 태그
2. keyword_1,2,3 있으면 → 레거시 태그
3. 둘 다 없으면 → branch_tags에서 자동 top3
```

## 5. 통합 수정 모드

### 5.1 UI 구조
- 보기 모드: [수정] 버튼 + [보류/승인/게시] 상태 버튼
- 수정 모드: [취소/저장] 버튼

### 5.2 수정 가능 항목
- 지역 (region)
- 태그 (keywords)
- 요약 (summary_all, summary_1y, summary_6m, summary_3m, summary_1m)

### 5.3 JavaScript 함수
| 함수 | 설명 |
|------|------|
| `enterEditMode()` | 수정 모드 진입 |
| `cancelEditMode()` | 수정 모드 취소 |
| `saveAllChanges(branchId)` | 모든 변경사항 저장 |
| `renderTagSelector()` | 태그 선택기 렌더링 |
| `toggleTag(tagName)` | 태그 선택/해제 |
| `addCustomTag()` | 커스텀 태그 추가 |
| `removeCustomTag(tagName)` | 커스텀 태그 삭제 |

## 6. 실시간 반영
- 저장 시 모달 UI 즉시 업데이트
- 대시보드 테이블 즉시 업데이트 (renderTable)
- DB 저장 (PUT /api/v2/summaries/{branch_id})

---

## 수정된 파일

| 파일 | 변경 내용 |
|------|----------|
| `web/templates/dashboard_v2.html` | 모달 UI 전면 개편, JavaScript 함수 추가/수정 |
| `web/app.py` | `/api/tags/batch` 쿼리 최적화 |

---

## API 엔드포인트

### PUT /api/v2/summaries/{branch_id}
```json
{
  "region": "서울 강남구",
  "keywords": ["고객응대", "차량상태", "커스텀태그"],
  "summary_all": "전체 요약...",
  "summary_1y": "1년 요약...",
  "summary_6m": "6개월 요약...",
  "summary_3m": "3개월 요약...",
  "summary_1m": "1개월 요약..."
}
```

### GET /api/tags/batch?branch_ids=1,2,3
- 여러 지점의 top3 태그 일괄 조회
- 최적화: 단일 쿼리로 모든 지점 조회
