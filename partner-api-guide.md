# Carmore AI 리포트 API 연동 가이드

파트너 프론트엔드에서 AI 리뷰 리포트를 조회, 생성, PDF 다운로드하기 위한 API 연동 문서입니다.

---

## 환경별 Base URL

| 환경 | Base URL | 비고 |
|------|----------|------|
| **DEV** | `http://localhost:8000/api` | 로컬 개발 서버 |
| **PROD** | `https://n8n-cloud.carmore.kr/review/api` | Nginx 프록시 경로 |

> 아래 모든 엔드포인트 경로는 Base URL 뒤에 붙입니다.
> 예: `GET {BASE_URL}/reports/123/review-count?start_date=2026-01-01&end_date=2026-03-31`

---

## 인증

> **참고**: 현재 Public API는 별도 인증 없이 접근 가능합니다. 향후 `X-API-Key` 헤더 인증이 추가될 수 있습니다.

---

## 응답 형식

### 성공

```json
{
  "success": true,
  "data": { ... }
}
```

### 실패

```json
{
  "detail": "에러 메시지"
}
```

HTTP 상태 코드: `400` (잘못된 요청), `404` (리소스 없음), `422` (파라미터 오류)

---

## 연동 플로우

```
1. 사용자가 'AI 리뷰' 버튼 클릭
2. 날짜 선택 모달 표시
3. GET /reports/{branch_id}/review-count → 리뷰 수 확인
   ├─ selected_count >= threshold(30) → 그대로 진행
   ├─ selected_count < threshold → recommended_period로 날짜 자동 전환
   └─ sufficient: false → "리뷰가 부족합니다" 안내, 생성 차단
4. POST /reports/{branch_id}/generate/async → job_id 받기
5. GET /reports/{branch_id}/job/{job_id} → 2초 간격 폴링 (최대 60회)
   ├─ status: "processing" → progress 표시, 계속 폴링
   ├─ status: "completed" → 다음 단계로
   └─ status: "failed" → 에러 표시
6. GET /reports/{branch_id} → 완성된 JSON 리포트 렌더링
7. PDF 버튼 클릭 → GET /reports/{branch_id}/pdf → 새 탭에서 다운로드
```

---

## API 엔드포인트

### 1. 리뷰 수 사전 확인

날짜 선택 직후 호출하여, 선택 기간에 리뷰가 충분한지 확인합니다.

```
GET /reports/{branch_id}/review-count?start_date={YYYY-MM-DD}&end_date={YYYY-MM-DD}
```

**응답 예시**

```json
{
  "success": true,
  "data": {
    "selected_count": 12,
    "period_counts": {
      "1m": 12,
      "3m": 35,
      "6m": 78,
      "12m": 150,
      "all": 320
    },
    "threshold": 30,
    "recommended_period": "3m",
    "sufficient": true
  }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `selected_count` | int | 선택한 기간의 리뷰 수 |
| `period_counts` | object | 표준 기간별 리뷰 수 (1m/3m/6m/12m/all) |
| `threshold` | int | 리포트 생성 최소 리뷰 수 (현재 30건) |
| `recommended_period` | string \| null | threshold 이상인 최단 기간 (예: "3m") |
| `sufficient` | bool | 어떤 기간이든 threshold 이상 리뷰가 존재하는지 |

**프론트엔드 처리 로직**

```javascript
const res = await fetch(`${BASE_URL}/reports/${branchId}/review-count?start_date=${startDate}&end_date=${endDate}`);
const { data } = await res.json();

if (data.selected_count < data.threshold) {
  if (data.recommended_period) {
    // 권장 기간으로 자동 전환
    // recommended_period 값("1m","3m","6m","12m","all")에 따라 날짜 재설정
    alert(`리뷰가 부족하여 ${data.recommended_period} 기간으로 전환합니다.`);
  } else {
    // 전체 기간도 30건 미만 → 생성 불가
    alert('리뷰가 부족하여 리포트를 생성할 수 없습니다.');
    return;
  }
}
```

### 2. 리포트 비동기 생성

리포트 생성은 AI 분석이 포함되어 시간이 걸리므로 비동기로 처리합니다.

```
POST /reports/{branch_id}/generate/async
Content-Type: application/json
```

**Request Body**

```json
{
  "start_date": "2026-01-01",
  "end_date": "2026-03-31"
}
```

> `output_config`, `data_config`, `prompt_config`는 선택적 고급 설정입니다.
> 생략하면 기본값이 적용됩니다.

**응답 예시 (202)**

```json
{
  "success": true,
  "data": {
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "poll_url": "/api/reports/123/job/550e8400-e29b-41d4-a716-446655440000"
  }
}
```

### 3. 생성 진행률 폴링

```
GET /reports/{branch_id}/job/{job_id}
```

**응답 예시**

```json
{
  "success": true,
  "data": {
    "status": "processing",
    "progress": 45
  }
}
```

| status | 설명 |
|--------|------|
| `"processing"` | 생성 중 (progress: 0~100) |
| `"completed"` | 완료 — 리포트 조회 가능 |
| `"failed"` | 실패 |

**폴링 구현 예시**

```javascript
async function pollJob(branchId, jobId) {
  const maxPolls = 60;
  for (let i = 0; i < maxPolls; i++) {
    const res = await fetch(`${BASE_URL}/reports/${branchId}/job/${jobId}`);
    const { data } = await res.json();

    if (data.status === 'completed') return true;
    if (data.status === 'failed') throw new Error('리포트 생성 실패');

    updateProgressBar(data.progress); // 0~100
    await new Promise(r => setTimeout(r, 2000)); // 2초 대기
  }
  throw new Error('시간 초과');
}
```

### 4. 리포트 조회

저장된 리포트가 있으면 즉시 반환, 없으면 자동 생성 후 반환합니다.

```
GET /reports/{branch_id}?start_date={YYYY-MM-DD}&end_date={YYYY-MM-DD}
```

> `period` 파라미터로도 조회 가능: `?period=3m` (1m/3m/6m/12m/1y/all)
> 기간 미지정 시 리뷰 수 기반 최적 기간 자동 선택

**응답**

```json
{
  "success": true,
  "data": {
    "branch_id": 123,
    "branch_name": "강남점",
    "affiliate_name": "카모어",
    "period_start": "2026-01-01",
    "period_end": "2026-03-31",
    "total_reviews": 45,
    "period_summary": "강남점은 직원 친절도에서 높은 평가를 받고 있으며...",

    "affiliate_evaluation": {
      "top_positive": [
        { "tag_name": "직원친절", "category_name": "서비스", "count": 12, "ratio": 80 }
      ],
      "top_negative": [
        { "tag_name": "청결", "category_name": "차량", "count": 5, "ratio": 33 }
      ],
      "ai_text": "업체 평가 AI 분석 텍스트"
    },

    "vehicle_evaluation": {
      "top_liked": [
        { "model": "아반떼", "count": 8, "ratio": 90, "tags": ["청결(85%)", "외관(72%)"] }
      ],
      "top_disliked": [
        { "model": "모닝", "count": 3, "ratio": 60, "tags": ["외관(40%)"] }
      ],
      "ai_text": "차량 평가 AI 분석 텍스트"
    },

    "benchmark": {
      "branch_rating": 4.2,
      "regional_avg_rating": 3.8,
      "regional_rank_pct": 25,
      "region_name": "서울",
      "total_branches_in_region": 40
    },

    "negative_reviews": [
      {
        "content": "차량 내부가 더러웠습니다",
        "rating": 2.0,
        "rating_car": 1.0,
        "rating_convenience": 2.0,
        "review_date": "2026-01-15",
        "vehicle_model": "아반떼"
      }
    ],

    "generated_at": "2026-03-27 14:00:00",
    "is_new": false,
    "resolved_period": null,
    "auto_detected": false
  }
}
```

### 5. PDF 다운로드

```
GET /reports/{branch_id}/pdf?start_date={YYYY-MM-DD}&end_date={YYYY-MM-DD}
```

> `period` 파라미터 사용 가능: `?period=3m`

**응답**: `application/pdf` 바이너리 (Content-Disposition: attachment)

**프론트엔드 구현**

```javascript
function downloadPDF(branchId, startDate, endDate) {
  const url = `${BASE_URL}/reports/${branchId}/pdf?start_date=${startDate}&end_date=${endDate}`;
  window.open(url, '_blank');
}
```

---

## 태그 라벨 매핑

API는 태그명(예: `"직원친절"`)을 반환합니다. 사용자에게 보여줄 때 아래 매핑을 사용하세요.

```javascript
const TAG_LABEL = {
  '직원친절':    { positive: '직원이 친절함',       negative: '직원이 불친절함' },
  '사고 처리':   { positive: '사고 처리를 잘해줌',   negative: '사고 처리를 잘 못해줌' },
  '배달/배차':   { positive: '배달/배차가 우수함',   negative: '배달/배차가 별로임' },
  '반납/픽업':   { positive: '반납/픽업이 원활함',   negative: '반납/픽업이 불편함' },
  '위치/접근성': { positive: '위치/접근성이 좋음',   negative: '위치/접근성이 불편함' },
  '가격':       { positive: '가격이 저렴함',        negative: '가격이 비쌈' },
  '주유비':     { positive: '주유비 부담 없음',     negative: '주유비 부담 있음' },
  '외관':       { positive: '차량 외관이 좋음',     negative: '차량 외관이 안좋음' },
  '청결':       { positive: '차량이 청결함',        negative: '차량이 불결함' },
};
```

---

## 고급 설정 (선택)

`POST /reports/{branch_id}/generate/async` 요청 시 아래 설정을 추가할 수 있습니다.

```json
{
  "start_date": "2026-01-01",
  "end_date": "2026-03-31",
  "output_config": {
    "include_period_summary": true,
    "include_affiliate_eval": true,
    "include_vehicle_eval": true,
    "include_benchmark": true,
    "summary_max_length": 300,
    "eval_max_length": 150
  },
  "data_config": {
    "include_tags": true,
    "include_vehicles": true,
    "include_sample_reviews": true,
    "sample_review_count": 10
  },
  "prompt_config": {
    "analysis_perspective": "operational",
    "tone": "analytical",
    "detail_level": "standard",
    "focus_areas": [],
    "temperature": 0.5,
    "custom_instruction": ""
  }
}
```

| 분석 관점 (`analysis_perspective`) | 설명 |
|---|---|
| `operational` | 운영 관점 (기본값) |
| `marketing` | 마케팅 관점 |
| `executive` | 경영진 보고 |
| `customer_service` | CS 품질 개선 |
| `investor` | 투자/사업성과 |
| `comparative` | 비교 분석 |

| 톤 (`tone`) | 설명 |
|---|---|
| `analytical` | 분석적 (기본값) |
| `friendly` | 친근한 |
| `formal` | 격식체 |
| `concise` | 간결한 |
| `data_driven` | 데이터 중심 |
| `narrative` | 서술형 |

| 상세 수준 (`detail_level`) | 요약 분량 | 평가 분량 |
|---|---|---|
| `brief` | 150자 | 100자 |
| `standard` | 300자 | 150자 |
| `detailed` | 600자 | 250자 |

모든 설정은 선택적이며, 생략 시 기본값이 적용됩니다.
