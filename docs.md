# Review Summary AI - 기술 문서

> Carmore 렌트카 22만 건 리뷰를 자동 분석하여 운영팀이 지점별 서비스 품질을 모니터링하는 대시보드 시스템.

---

## 1. 아키텍처

```
Request -> API (endpoints) -> Service -> Domain / Repository -> Response
                                |
                           Infrastructure (OpenAI, Athena, PDF)
```

| 레이어 | 역할 | 경로 |
|--------|------|------|
| API | HTTP 라우팅, 인증 | `app/api/v1/endpoints/` |
| Service | 비즈니스 로직, 트랜잭션 | `app/services/` |
| Domain | NLP 분석, 파이프라인 | `app/domain/` |
| Repository | DB 접근 (SQLAlchemy Async) | `app/repository/` |
| Infrastructure | 외부 시스템 (OpenAI, AWS, PDF) | `app/infrastructure/` |

**경계 규칙**: Domain은 외부 API를 직접 호출하지 않는다. 필요한 데이터는 Service가 주입하고, Domain은 계산만 담당.

### 기술 스택

| 영역 | 기술 |
|------|------|
| Backend | Python 3.12, FastAPI, Uvicorn |
| NLP | Kiwi (형태소 분석), FastEmbed (ONNX 임베딩) |
| LLM | OpenAI GPT-4o-mini |
| DB | PostgreSQL, SQLAlchemy Async, asyncpg, Alembic |
| PDF | WeasyPrint (프로덕션), fpdf2 (폰트 폴백) |
| Frontend | Jinja2, Vanilla JS |

### 핵심 기능

| 기능 | 설명 | 주요 컴포넌트 |
|------|------|---------------|
| 리뷰 동기화 | Athena -> PostgreSQL 동기화 | SyncService, UnifiedPipeline |
| 감정 분석 | 리뷰별 긍정/부정/중립 판정 | ABSA, HybridClassifier |
| 태그 분류 | 52개 세분화 태그 자동 분류 | HybridClassifier (규칙 + FastEmbed) |
| AI 요약 | 지점별 기간 요약 (1m/3m/6m/1y/all) | SummaryGenerator, GPT-4o-mini |
| 컨설팅 리포트 | 4단계 파이프라인 + PDF | ReportService, ReportAIGenerator |

---

## 2. 핵심 워크플로우

### 리뷰 동기화 (`sync_reviews`)

```
sync_reviews(date_from, date_to)
  -> 날짜를 1일 단위 청크로 분할
  -> for each day_chunk:
       AthenaClient.fetch_reviews(since, until)
       -> 중복 제거 (review_id 기준)
       -> 오배정 필터링 (branch_id당 다수 업체 80% 기준)
       -> branch_reviews UPSERT (즉시 commit, 데드락 방지)
       -> UnifiedPipeline.run(new_reviews)
```

### 배치 파이프라인 (`UnifiedPipeline.run`) - 9단계

| Step | 클래스 | 역할 | 실패 시 |
|------|--------|------|---------|
| 1 | ReviewPreprocessor | 전처리 + 키워드 추출 + 감정 분석 + 태그 분류 | 전체 중단 |
| 2 | ReviewSentimentUpdater | sentiment 배치 UPDATE | 다음 단계 |
| 4 | TagAggregator | tags + branch_tags 갱신 | Step 7,8,9 스킵 |
| 5 | CarModelTagAggregator | 차량 모델 갱신 | 다음 단계 |
| 6 | KeywordManager | branch_keywords 갱신 | 다음 단계 |
| 7 | ReviewTagMapper | review_tag_mappings 저장 | 다음 단계 |
| 8 | MonthlyStatsUpdater | monthly_*_stats 갱신 | 다음 단계 |
| 9 | MonthlyCarModelStatsUpdater | 차량 월별 태그 통계 | 종료 |

> Step 3은 사용되지 않음 (번호 건너뜀). 각 단계는 savepoint로 격리되어 부분 롤백 가능.

### AI 요약 생성 (`generate_summary_with_data`)

```
1. 기간 선택: 1m -> 3m -> 6m -> 1y -> all (30건 이상인 첫 기간)
2. 태그 통계 + 감정 통계 조회
3. 감정별 대표 리뷰 샘플링
4. OpenAI GPT-4o-mini 호출
5. 후처리: 마크다운 제거 + 숫자 할루시네이션 교정
6. branch_summaries 저장
```

### 리포트 생성 (`generate_report_with_progress`) - 4단계

```
Step 1 (10%): 지점 정보 + 차량 분석 수집
Step 2 (35%): TagStatsCalculator - 카테고리별 집계, 강점/개선점 판정
Step 2.5 (55%): 트렌드 비교, 벤치마크, 우선순위 액션
Step 3 (80%): ReportAIGenerator - LLM 3회 호출 (기간 요약 + 업체 평가 + 차량 평가)
Step 4 (100%): ReportData 조립 + DB 저장 + PDF 생성
```

캐시 무효화: 새 리뷰 30건 이상, 태그 비율 15% 변동, 감정 drift 8% 초과 시 재생성.

---

## 3. 분석 엔진

### ABSA (절 단위 감정 분석)

```
입력: "직원이 친절했지만 차량이 더러웠어요"
  -> 절 분리: ["직원이 친절했지만", "차량이 더러웠어요"]
  -> 절별: Aspect 추출 -> 감정 판정
  -> 출력: [{aspect: "직원친절", sentiment: positive}, {aspect: "청결", sentiment: negative}]
```

**감정 판정 우선순위:**

1. 이중부정 (0.95) -- "불편하지 않다" -> 긍정
2. 부정어+긍정어 (0.85) -- "친절하지 않다" -> 부정
3. 명확한 부정 키워드 -- 다수결
4. 긍정 예외 (0.80) -- "틀림없", "끄떡없"
5. 반전 구문 감지 -- "~지만", "~는데" -> 뒤쪽 감정 우선
6. 일반 패턴 매칭 -- 긍정/부정 regex 다수결

### HybridClassifier (태그 분류)

```
키워드 입력
  -> [1] 범용 키워드 체크 ("상태", "필요" 등 -> 규칙만)
  -> [2] 규칙 기반 매핑 (O(1) 정확일치 -> 어간일치 -> 부분문자열)
  -> [3] 임베딩 분류 (FastEmbed 코사인 유사도, 임계값 0.50)
  -> [4] 충돌 해소 (pos+neg 공존 -> 반전 구문이면 neg 제거, 아니면 다수결)
```

**리뷰 분류 흐름:**
1. ABSA 분석 (우선) -> 분류된 키워드 수집
2. 미분류 키워드만 임베딩 배치 분류
3. 양보/반전 구문 감지 + 충돌 해소
4. 카테고리별 키워드 상한 (MAX_KEYWORDS_PER_CATEGORY = 3)

### 통합 감정 분석 (텍스트 + 평점)

| 조건 | 결과 |
|------|------|
| min_rating < 3.0 | negative 또는 neutral |
| 텍스트 = 평점 (합의) | 합의 결과 유지 |
| 텍스트=negative, avg >= 4.0 | neutral |
| 텍스트=positive, avg < 3.5 | neutral |
| 기타 | 텍스트 우선 (x0.9 감쇄) |

가중치: ABSA 30%, HybridClassifier 40%, 평점 별도 규칙.

### 태그 시스템

9개 카테고리, 52개 태그:

| 카테고리 | 긍정 표현 | 부정 표현 |
|----------|-----------|-----------|
| 직원친절 | 직원이 친절함 | 직원이 불친절함 |
| 외관 | 차량외관이 좋음 | 차량외관이 별로임 |
| 가격 | 가격이 저렴함 | 가격이 비쌈 |
| 청결 | 차량이 청결함 | 차량이 더러움 |
| 사고 처리 | 사고 처리를 잘해줌 | 사고 처리가 별로임 |
| 주유비 | 주유비 부담 없음 | 주유비 부담 높음 |
| 배달/배차 | 배달/배차가 우수함 | 배달/배차가 별로임 |
| 반납/픽업 | 반납/픽업이 원활함 | 반납/픽업이 불편함 |
| 위치/접근성 | 위치/접근성이 좋음 | 위치/접근성이 불편함 |

---

## 4. 파트너 API 연동

### Base URL

| 환경 | URL |
|------|-----|
| DEV | `http://localhost:8000/api` |
| PROD | `https://n8n-cloud.carmore.kr/review/api` |

### 연동 플로우

```
1. GET /reports/{branch_id}/review-count  -> 리뷰 수 확인
   - selected_count >= 30 -> 진행
   - selected_count < 30, recommended_period 있음 -> 기간 자동 전환
   - sufficient: false -> 생성 차단
2. POST /reports/{branch_id}/generate/async  -> job_id 받기
3. GET /reports/{branch_id}/job/{job_id}  -> 2초 간격 폴링 (최대 60회)
4. GET /reports/{branch_id}  -> 완성된 JSON 리포트
5. GET /reports/{branch_id}/pdf  -> PDF 다운로드
```

### 엔드포인트

#### 리뷰 수 확인

```
GET /reports/{branch_id}/review-count?start_date=2026-01-01&end_date=2026-03-31
```

```json
{
  "success": true,
  "data": {
    "selected_count": 12,
    "period_counts": { "1m": 12, "3m": 35, "6m": 78, "12m": 150, "all": 320 },
    "threshold": 30,
    "recommended_period": "3m",
    "sufficient": true
  }
}
```

#### 리포트 생성 (비동기)

```
POST /reports/{branch_id}/generate/async
Body: { "start_date": "2026-01-01", "end_date": "2026-03-31" }
```

```json
{
  "success": true,
  "data": { "job_id": "550e8400-...", "poll_url": "/api/reports/123/job/550e8400-..." }
}
```

#### 진행률 폴링

```
GET /reports/{branch_id}/job/{job_id}
```

| status | 설명 |
|--------|------|
| `processing` | 생성 중 (progress: 0~100) |
| `completed` | 완료 |
| `failed` | 실패 |

#### 리포트 조회

```
GET /reports/{branch_id}?start_date=2026-01-01&end_date=2026-03-31
```

> `?period=3m` (1m/3m/6m/12m/1y/all) 으로도 조회 가능. 기간 미지정 시 최적 기간 자동 선택.

응답에 포함되는 주요 필드: `period_summary`, `affiliate_evaluation` (강점/개선점 + AI 텍스트), `vehicle_evaluation` (인기/불만 차량 + AI 텍스트), `benchmark` (지역 평균 대비), `negative_reviews` (부정 리뷰 샘플).

#### PDF 다운로드

```
GET /reports/{branch_id}/pdf?start_date=2026-01-01&end_date=2026-03-31
```

응답: `application/pdf` 바이너리.

### 태그 라벨 매핑

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

### 고급 설정 (선택)

리포트 생성 시 `output_config`, `data_config`, `prompt_config`를 추가할 수 있다. 생략 시 기본값 적용.

| 설정 | 주요 옵션 |
|------|-----------|
| `prompt_config.analysis_perspective` | `operational` (기본), `marketing`, `executive`, `customer_service` |
| `prompt_config.tone` | `analytical` (기본), `friendly`, `formal`, `concise` |
| `prompt_config.detail_level` | `brief` (150자), `standard` (300자), `detailed` (600자) |

---

## 5. 에러 처리

### 원칙: 단계별 격리

각 단계의 실패가 이전 단계의 성공을 되돌리지 않는다.

| 서비스 | 실패 시 | 폴백 |
|--------|---------|------|
| SyncService (청크) | chunk_errors 누적 | 부분 성공 응답 |
| UnifiedPipeline (단계별) | success=False 기록 | 다음 단계 진행 |
| SummaryGenerator (리뷰 부족) | `{"success": false}` | 에러 메시지 |
| ReportAIGenerator (LLM 실패) | Exception 포착 | fallback 기본 텍스트 |
| AnalysisService (Athena 실패) | ConnectionError | PostgreSQL 폴백 |
| HybridClassifier (임베딩 실패) | RuntimeError | 규칙만 사용 |

### DB 연결 재시도

```python
@with_retry(max_attempts=3, min_wait=0.5, max_wait=4.0)
# Exponential backoff: asyncpg 연결 오류, OperationalError, OSError 대상
```

---

## 6. 트러블슈팅

### 동기화 안 됨

| 증상 | 해결 |
|------|------|
| `Athena 클라이언트가 설정되지 않았습니다` | `.env`에 AWS 키 설정 |
| asyncpg 에러 | `DATABASE_URL` 확인, PostgreSQL 실행 확인 |
| 이미 실행 중 | sync_metadata 잠금 -- 이전 동기화 완료 대기 |

### AI 요약 안 됨

| 증상 | 해결 |
|------|------|
| `{"success": false}` | 최소 30건 리뷰 필요 |
| 500 에러 | `OPENAI_API_KEY` 확인 |
| 429 에러 | Rate limit -- `OPENAI_RPM` 확인 |

### 태그 분류 이상

| 증상 | 해결 |
|------|------|
| 항상 "기타" | 임베딩 유사도 < 0.50. `/tag-tester`에서 테스트 |
| 잘못된 태그 | `patterns.py` RULE_BASED_TAG_MAPPING 확인 |
| 감정 반전 | CONCESSION_REGEX 패턴 확인 |

### 리포트 생성 실패

| 증상 | 해결 |
|------|------|
| 태그 통계 없음 | 해당 지점 파이프라인 재실행 |
| PDF 생성 실패 | 폰트 파일 존재 여부 확인 |
| 캐시 미갱신 | 새 리뷰 30건 이상이면 자동 재생성 |

---

## 7. 주요 상수

| 상수 | 값 | 용도 |
|------|-----|------|
| `SIMILARITY_THRESHOLD` | 0.50 | 임베딩 유사도 최소값 |
| `CONTEXT_WINDOW_SIZE` | 50 | 감정 분석 문맥 윈도우 (글자) |
| `MIN_REVIEWS_FOR_SUMMARY` | 30 | 요약 생성 최소 리뷰 수 |
| `WEIGHT_RULE_BASED` | 0.3 | ABSA 감정 가중치 |
| `WEIGHT_HYBRID` | 0.4 | HybridClassifier 감정 가중치 |
| `MAX_KEYWORDS_PER_CATEGORY` | 3 | 리뷰당 태그별 최대 키워드 |
| `EMBEDDING_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | FastEmbed 모델 |

---

## 8. 용어 사전

| 용어 | 설명 |
|------|------|
| ABSA | Aspect-Based Sentiment Analysis. 태그별로 분리하여 각각 감정 분석 |
| `branch_id` | 렌트카 지점 고유번호 |
| `tag_sentiments` | `{태그명: {"positive": [], "negative": [], "neutral": []}}` |
| CLT | Change List Threshold. 리포트 캐시 무효화 기준 (새 리뷰 30건) |
| Athena | AWS Athena. 리뷰 원본이 저장된 데이터 레이크 |
| Kiwi | 한국어 형태소 분석기 (C++ 기반, 스레드 안전 아님 -> Lock 보호) |
| FastEmbed | ONNX 기반 경량 임베딩 모델. 태그 유사도 계산 |
| 이중부정 | "불편하지 않다" -> 긍정 |
| 양보/반전 구문 | "~지만", "~는데" -> 뒤쪽 감정 우선 |
| Ghost review | Athena에 없고 PostgreSQL에만 남은 리뷰 |
| 오배정 | branch_id에 여러 업체 리뷰 혼재. 80% 기준 소수 업체 제거 |
