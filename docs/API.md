# Review Summary AI - API 문서

Flask 기반 REST API 문서입니다.

## Base URL

```
http://localhost:5000
```

---

## 보안

### IP 화이트리스트

모든 API는 IP 화이트리스트로 보호됩니다.

| 환경변수 | 설명 | 기본값 |
|----------|------|--------|
| `IP_WHITELIST` | 허용 IP (쉼표 구분, CIDR 지원) | `127.0.0.1,::1` |
| `IP_WHITELIST_ENABLED` | 활성화 여부 | `true` |
| `TRUST_PROXY` | 프록시 뒤 실행 시 | `false` |
| `PROXY_DEPTH` | X-Forwarded-For 신뢰 깊이 | `1` |
| `FLASK_DEBUG` | 디버그 모드 | `false` |

**예시:**
```bash
# 사내망 허용
IP_WHITELIST=127.0.0.1,::1,192.168.1.0/24,10.0.0.0/8
```

**차단 시 응답:**
```json
{"error": "Access denied: IP not in whitelist"}
```
Status: `403 Forbidden`

---

## 요약 관리 (Summaries)

### GET /api/summaries
전체 요약 목록 조회

**Query Parameters:**
| 파라미터 | 타입 | 설명 | 기본값 |
|----------|------|------|--------|
| `status` | string | `draft`, `approved`, `published` | - |
| `period` | string | `all`, `1m`, `3m`, `6m`, `1y` | `all` |
| `category_id` | int | 카테고리 ID 필터 | - |
| `tag_id` | int | 태그 ID 필터 | - |
| `limit` | int | 페이지 크기 | `50` |
| `offset` | int | 오프셋 | `0` |

**예시:**
```bash
curl "http://localhost:5000/api/summaries?status=draft&limit=10"
```

---

### GET /api/summaries/:id
특정 요약 상세 조회

**예시:**
```bash
curl http://localhost:5000/api/summaries/123
```

---

### PUT /api/summaries/:id
요약 수정

**Body:**
```json
{
  "edited_summary": "수정된 요약 내용",
  "status": "draft"
}
```

**허용 필드:** `edited_summary`, `status`

---

### POST /api/summaries/:id/approve
요약 승인 (`draft` → `approved`)

```bash
curl -X POST http://localhost:5000/api/summaries/123/approve
```

---

### POST /api/summaries/:id/publish
요약 게시 (`approved` → `published`)

```bash
curl -X POST http://localhost:5000/api/summaries/123/publish
```

---

### POST /api/summaries/:id/draft
요약을 draft로 되돌리기

```bash
curl -X POST http://localhost:5000/api/summaries/123/draft
```

---

## 통계 (Stats)

### GET /api/stats
통계 정보 조회

**Query Parameters:**
| 파라미터 | 타입 | 설명 | 기본값 |
|----------|------|------|--------|
| `period` | string | `all`, `1m`, `3m`, `6m`, `1y` | `all` |

**응답:**
```json
{
  "total": 1234,
  "draft": 100,
  "approved": 500,
  "published": 634
}
```

---

## 카테고리 관리 (Categories)

### GET /api/categories
카테고리 목록

**Query Parameters:**
| 파라미터 | 타입 | 설명 | 기본값 |
|----------|------|------|--------|
| `is_active` | bool | 활성 카테고리만 | `true` |

---

### GET /api/categories/:id
카테고리 상세

---

### POST /api/categories
카테고리 생성

**Body:**
```json
{
  "name": "카테고리명",
  "description": "설명",
  "color": "#10b981",
  "display_order": 1
}
```

---

### PUT /api/categories/:id
카테고리 수정

---

### DELETE /api/categories/:id
카테고리 삭제

---

## 태그 관리 (Tags)

### GET /api/tags
태그 목록

**Query Parameters:**
| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `group_name` | string | 그룹 필터 (예: `서비스`, `차량`) |
| `sentiment` | string | `positive`, `negative`, `neutral` |
| `category_id` | int | 카테고리 필터 (deprecated) |

---

### GET /api/tags/:id
태그 상세

---

### POST /api/tags
태그 생성

**Body:**
```json
{
  "name": "친절한 직원",
  "group_name": "서비스",
  "color": "#10b981",
  "sentiment": "positive"
}
```

---

### PUT /api/tags/:id
태그 수정

---

### DELETE /api/tags/:id
태그 삭제

---

### GET /api/tags/:id/keywords
태그에 매핑된 키워드 목록

---

### GET /api/tags/groups
태그 그룹 목록 (고유한 group_name들)

**응답:**
```json
[
  {"group_name": "서비스", "color": "#10b981", "count": 15},
  {"group_name": "차량", "color": "#3b82f6", "count": 12}
]
```

---

## 키워드-태그 매핑 (Mappings)

### GET /api/mappings
매핑 목록

**Query Parameters:**
| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `tag_id` | int | 태그 ID 필터 |
| `keyword` | string | 키워드 필터 |

---

### POST /api/mappings
매핑 생성

**Body:**
```json
{
  "keyword": "친절",
  "tag_id": 5,
  "is_auto": false
}
```

---

### DELETE /api/mappings/:id
매핑 삭제

---

### GET /api/mappings/unmapped
매핑되지 않은 키워드 목록

**Query Parameters:**
| 파라미터 | 타입 | 설명 | 기본값 |
|----------|------|------|--------|
| `limit` | int | 결과 제한 | `100` |

---

### POST /api/mappings/bulk
매핑 일괄 생성

**Body:**
```json
{
  "mappings": [
    {"keyword": "친절", "tag_id": 5},
    {"keyword": "빠른", "tag_id": 6}
  ]
}
```

---

### POST /api/mappings/auto
자동 매핑 실행 (TagMapper 사용)

```bash
curl -X POST http://localhost:5000/api/mappings/auto
```

---

## 지점별 조회 (Branch)

### GET /api/branch/:id
지점별 요약 조회

---

### GET /api/branch/:id/tags
지점별 태그 목록

**Query Parameters:**
| 파라미터 | 타입 | 설명 | 기본값 |
|----------|------|------|--------|
| `period` | string | `all`, `1m`, `3m`, `6m`, `1y` | `all` |
| `limit` | int | 상위 N개 | `10` |

---

### GET /api/branch/:id/periods
지점의 모든 기간별 요약

---

## 스케줄러 관리 (Scheduler)

### GET /api/scheduler/status
스케줄러 상태 조회

**응답:**
```json
{
  "running": true,
  "jobs": [
    {"id": "incremental_pipeline", "next_run": "2026-01-17T00:00:00"}
  ]
}
```

---

### GET /api/scheduler/config
스케줄 설정 조회

---

### PUT /api/scheduler/config/:key
스케줄 설정 업데이트

**Body:**
```json
{
  "cron_expression": "0 0 * * *",
  "is_enabled": true
}
```

---

### POST /api/scheduler/trigger
스케줄러 수동 실행

**Body:**
```json
{
  "config_key": "incremental_pipeline",
  "mode": "incremental"
}
```

| mode | 설명 |
|------|------|
| `incremental` | API 신규 리뷰만 처리 |
| `batch` | Excel 전체 처리 |

---

### POST /api/scheduler/trigger/batch
배치 파이프라인 수동 실행 (Excel 전체 - 초기 1회용)

---

### POST /api/scheduler/trigger/incremental
증분 파이프라인 수동 실행 (API 신규 리뷰만)

---

### POST /api/scheduler/test
스케줄러 테스트 실행 (파이프라인 없이 로그만)

---

### GET /api/scheduler/logs
실행 로그 조회

**Query Parameters:**
| 파라미터 | 타입 | 기본값 |
|----------|------|--------|
| `limit` | int | `20` |

---

### GET /api/scheduler/last-run
마지막 실행 정보

**Query Parameters:**
| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `config_key` | string | 스케줄 키 |

---

## 감정 분석 (Sentiment)

### GET /api/sentiment/stats
지점별 감정태그 통계

**Query Parameters:**
| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `branch_id` | int | 지점번호 (없으면 전체) |

**응답:**
```json
{
  "positive": 850,
  "negative": 120,
  "neutral": 30,
  "total": 1000,
  "positive_ratio": 85.0,
  "negative_ratio": 12.0
}
```

---

### GET /api/sentiment/stats/all
전체 지점 감정통계 목록

---

## 리뷰 관리 (Reviews)

### GET /api/reviews/recent
최근 리뷰 검색 (1개월치)

**Query Parameters:**
| 파라미터 | 타입 | 설명 | 기본값 |
|----------|------|------|--------|
| `sentiment` | string | `positive`, `negative`, `neutral` | - |
| `branch_id` | int | 지점번호 | - |
| `limit` | int | 결과 제한 (최대 1000) | `100` |
| `offset` | int | 페이지네이션 | `0` |

**응답:**
```json
{
  "reviews": [...],
  "total": 1234,
  "stats": {
    "positive": 800,
    "negative": 100,
    "neutral": 334
  }
}
```

---

### POST /api/reviews/cleanup
오래된 리뷰 정리

**Body:**
```json
{
  "days": 30,
  "max_per_branch": 30
}
```

**응답:**
```json
{
  "old_deleted": 150,
  "excess_deleted": 45,
  "total": 195,
  "message": "30일 이전 150개, 지점당 초과분 45개 삭제됨"
}
```

---

## 에러 응답

모든 API는 에러 시 다음 형식으로 응답합니다:

```json
{
  "error": "에러 메시지"
}
```

| Status Code | 설명 |
|-------------|------|
| `400` | 잘못된 요청 (파라미터 오류) |
| `403` | 접근 거부 (IP 차단) |
| `404` | 리소스 없음 |
| `500` | 서버 오류 |

---

## 빠른 테스트

```bash
# 통계 조회
curl http://localhost:5000/api/stats

# 요약 목록 (draft 상태)
curl "http://localhost:5000/api/summaries?status=draft&limit=5"

# 태그 목록
curl http://localhost:5000/api/tags

# 스케줄러 상태
curl http://localhost:5000/api/scheduler/status

# 감정 통계
curl http://localhost:5000/api/sentiment/stats
```
