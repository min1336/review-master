# Findings

연구 결과, API 문서, 코드 분석 등을 저장하는 파일. 컨텍스트 비대화 방지.

---

## Architecture

### Project Structure
```
src/
├── analysis/           # 감성 분석 & 키워드 모듈
│   ├── sentiment/      # Lexicon, BERT, Hybrid 분석기
│   ├── keywords/       # MeCab 추출, 가중치 계산
│   ├── chunking/       # 절 단위 텍스트 청킹
│   └── tags/           # 태그 매핑 & 임베딩 분류기
├── config/             # 설정, 불용어
├── llm/                # OpenAI & Gemini 프로바이더
├── pipeline/           # 배치 처리 오케스트레이션
├── db/                 # 데이터베이스 연결
└── preprocessing/      # 데이터 정제
```

### Key Constants
- `MIN_REVIEWS_PER_BRANCH = 30`
- `EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"`
- `SIMILARITY_THRESHOLD = 0.3` (태그 분류 최소 유사도)

---

## Code Analysis

### Sentiment Analysis Flow (v5.0)
- 리뷰별 감정분석 제거
- 키워드별 규칙 패턴 매칭으로 대체
- 부정 패턴: `불친절`, `비싸`, `냄새`, `아쉬운` 등
- 긍정 예외: `틀림없`, `변함없`, `번화가` 등

### Pipeline Flow (v5.0)
1. Excel 로드 (88K 리뷰 - 매핑 완료 파일)
2. 키워드 추출 (청킹 + MeCab)
3. 태그+감정 분류 (임베딩 + 규칙 패턴)
4. 키워드 집계 + LLM 요약 (태그별 감정 정보 활용)
5. Supabase 저장

---

## API Documentation

### External APIs
- **OpenAI**: GPT-3.5-turbo (3500 RPM)
- **Gemini**: gemini-2.5 (15 RPM)
- **Supabase**: PostgreSQL via REST API

### Internal Endpoints
See `docs/CARMORE_API.md` for full API documentation.

---

## Research Notes

### 2026-01-16: 차량별 리뷰 분류 가능성 조사

#### 배경
차량(모델)별로 리뷰 태그를 분류할 수 있는지 검토

#### 조사 결과

**1. 현재 Excel 데이터 (217K 리뷰)**

| 컬럼 | 차량 정보 |
|------|----------|
| 지점번호 | ✅ 있음 |
| 차량평점 | ✅ 있음 (1-5점) |
| 예약번호 | ✅ 있음 |
| **차량 모델** | ❌ **없음** |

```
# Excel 컬럼 목록
['리뷰번호', '예약번호', '유저인덱스', '회사번호', '지점번호',
 '지점평점(친절/편의성)', '차량평점', '인수/반납편의성', '리뷰내용',
 '원본리뷰내용', '욕설포함여부', '도움돼요수', '등록일시', '리뷰상태',
 '블라인드사유코드', '블라인드사유내용', '관리자확인여부', '제휴유형']
```

**2. Carmore API 리뷰 응답 (차량 정보 포함)**

```json
{
  "reviews": [{
    "carEvaluation": 5,
    "reservation": {
      "carModel": "모닝 3세대 F/L",   // ← 차량 모델명 포함!
      "rentType": "SHORT",             // ← 렌트 타입 포함
      "rentalStartDate": "2025-04-14T01:00:00.000Z",
      "rentalEndDate": "2025-04-15T01:00:00.000Z"
    }
  }]
}
```

**3. 차량 모델 마스터 API**

```
GET /cars/models 응답:
- id: 44, model: "현대 아반떼", type: "SEMI-MEDIUM", brand: "글로벌"
- id: 96, model: "오피러스 1세대", type: "LARGE", brand: "기아"
- id: 410, model: "포드 익스플로러", type: "SUV", brand: "글로벌"
...
```

**4. 기존 인프라 준비 상태**

| 항목 | 상태 | 위치 |
|------|------|------|
| car_models 테이블 스키마 | ✅ 준비됨 | `scripts/sql/create_enrichment_tables.sql` |
| get_car_models() API | ✅ 구현됨 | `src/api/carmore_client.py:339` |
| sync_car_models_from_api() | ✅ 구현됨 | `web/supabase_client.py:700` |
| 파이프라인 차량 분류 | ❌ 미구현 | - |

#### 결론

| 데이터 소스 | 차량별 분류 | 비고 |
|------------|------------|------|
| Excel (기존 217K) | ❌ 불가 | 차량 정보 컬럼 없음 |
| API (신규 리뷰) | ✅ 가능 | `reservation.carModel` 활용 |

#### 향후 구현 방안 (보류)

**API 기반 신규 리뷰 수집 시 구현:**

```python
# 파이프라인 확장 예시
for branch_id in branches:
    reviews = api.get_reviews(branch_id)
    for review in reviews:
        car_model = review['reservation']['carModel']  # ← 차량 모델
        rent_type = review['reservation']['rentType']  # ← 렌트 타입
        # 차량별 키워드 집계...
```

**필요 작업:**
1. API 기반 리뷰 수집 스크립트 작성
2. `car_model` 컬럼 추가 (recent_reviews 테이블)
3. 파이프라인에 차량별 집계 로직 추가
4. 차량별 요약/태그 생성

**참고:** 현재는 지점별 분류만 지원. 차량별 분류는 추후 API 기반 수집 전환 시 구현 예정.

---

### 2026-01-17: 시스템 단순화 변경 사항

#### 1. 태그 시스템 단순화 (완료)
- **이전**: 키워드 → 태그 → 카테고리 (3티어)
- **이후**: 키워드 → 태그 (2티어, group_name/color 내장)

#### 2. 제거 예정 기능
| 기능 | 파일 | 이유 |
|------|------|------|
| weighted_score | branch_tags, supabase_client | 불필요한 복잡도 |
| Gemini 프로바이더 | src/llm/, .env | OpenAI만 사용 |

#### 3. 개선 예정 기능
| 기능 | 현재 | 변경 |
|------|------|------|
| 리뷰 샘플 저장 | 무제한 | 30개/지점, 1개월 후 삭제 |
| LLM 프롬프트 | 기본 예시 | 개선된 출력 예시 |
| 스케줄러 | 단순 cron | API 연동 + 지점별/시기별 업데이트 |

#### 4. API 엔드포인트 외부 접근

**Q: 다른 곳에서 API를 사용해서 데이터를 불러올 수 있나요?**

**A: 예, 가능합니다.**

```python
# 현재 설정 (web/app.py)
app.run(host='0.0.0.0', port=5000)  # 모든 네트워크 인터페이스에서 접근 가능
```

**접근 방법:**
```bash
# 같은 네트워크 내 다른 컴퓨터에서
curl http://<서버IP>:5000/api/summaries

# 예시
curl http://192.168.1.100:5000/api/tags
curl http://192.168.1.100:5000/api/summaries?period=1m
```

**외부 서비스 연동 예시:**
```python
import requests

# 다른 Python 애플리케이션에서
response = requests.get('http://서버IP:5000/api/summaries')
data = response.json()

# n8n, Make(Integromat) 등 자동화 도구에서도 사용 가능
```

**보안 고려사항:**
- 현재: 인증 없음 (개발 환경용)
- 프로덕션: API Key 또는 JWT 인증 추가 권장
- 방화벽: 5000번 포트 개방 필요

**프로덕션 배포 시:**
1. Nginx/Apache 리버스 프록시 사용
2. HTTPS 적용
3. API 인증 추가
4. Rate Limiting 적용

#### 5. 스케줄러 개선 설계

**현재 구조:**
```
[Cron 스케줄] → [파이프라인 실행] → [전체 지점 일괄 업데이트]
- 성수기: 매일 새벽 3시
- 일반기: 주 3회
- 비수기: 주 1회
```

**개선 목표:**
```
[API 리뷰 수집] → [리뷰 누적] → [조건 충족 시 업데이트]
                                 ↓
                    지점별 + 시기별 개별 업데이트
```

**개선된 구조 설계:**

1. **리뷰 수집 레이어**
   ```
   Carmore API → recent_reviews 테이블 (30개/지점, 1개월 유지)
   - 주기: 매 시간 또는 매일
   - 동작: 신규 리뷰만 가져와서 저장
   ```

2. **업데이트 트리거 조건**
   ```python
   # 지점별 업데이트 조건
   - 신규 리뷰 10개 이상 누적 시
   - 마지막 업데이트 후 7일 경과 시
   - 수동 트리거 시

   # 시기별 업데이트
   - 1m: 매일 갱신 (최근 30일 데이터)
   - 3m: 주 1회 갱신
   - 6m: 월 1회 갱신
   - 1y: 분기 1회 갱신
   - all: 월 1회 갱신
   ```

3. **지점 그룹핑 (추후 확장)**
   ```
   위치 기반 그룹:
   - 공항권: 인천공항, 김포공항, 제주공항...
   - 제주권: 제주시, 서귀포...
   - 수도권: 서울, 경기...
   - 지방권: 부산, 대구...

   → 그룹별 스케줄 차등화 가능
   ```

4. **구현 우선순위**
   ```
   Phase 1: API 리뷰 수집 자동화 (cron)
   Phase 2: 조건 기반 업데이트 트리거
   Phase 3: 시기별 자동 갱신
   Phase 4: 위치 기반 그룹핑
   ```

**필요한 DB 변경:**
```sql
-- branch_update_status 테이블 (업데이트 추적용)
CREATE TABLE branch_update_status (
    branch_id INTEGER PRIMARY KEY,
    last_updated_at TIMESTAMPTZ,
    pending_reviews INTEGER DEFAULT 0,
    next_update_at TIMESTAMPTZ
);
```

---

### 2026-01-19: 파이프라인 v5.0 - 감정분석 제거

#### 배경
리뷰별 감정분석(Lexicon + BERT)이 파이프라인의 주요 병목. 키워드별 감정 판단으로 대체하여 성능 개선.

#### 변경 내용

**1. 제거된 기능**
- Step 2: 2단계 하이브리드 감정분석 (Lexicon → BERT)
- 대표 리뷰 선택 시 감정 기반 필터링

**2. 대체된 방식**
```python
# 이전: 리뷰별 감정분석
results = sentiment_analyzer.analyze_batch(texts)  # BERT 호출

# 이후: 키워드별 규칙 패턴 매칭
NEGATIVE_PATTERNS = ['불친절', '비싸', '냄새', '아쉬운', ...]
sentiment = 'negative' if pattern_match(keyword) else 'positive'
```

**3. 파이프라인 구조 변경**
```
v4.0 (5단계)                    v5.0 (4단계)
─────────────                   ─────────────
[1] 데이터 로드                  [1] 데이터 로드
[2] 감정 분석 (BERT)  ← 제거     [2] 키워드 추출
[3] 키워드 추출                  [3] 태그+감정+요약
[4] 집계+요약                    [4] DB 저장
[5] DB 저장
```

#### 성능 비교

| 버전 | 감정 분석 | 소요 시간 | 개선율 |
|------|----------|----------|--------|
| v4.0 | Lexicon + BERT | ~320초 | - |
| v5.0 | 키워드 패턴 | ~56초 | **6배 향상** |

#### 수정된 파일
- `src/pipeline/batch_pipeline.py`: `_analyze_sentiment()` 호출 제거
- `_get_representative_reviews()`: 감정 기반 → 키워드 기반 선택

---

### 2026-01-19: 청킹 + 임베딩 태그 분류 기능 구현

#### 배경
리뷰 텍스트를 의미 단위로 분리하고, BERT 임베딩 유사도 기반으로 키워드를 태그 그룹에 자동 분류

#### 구현된 기능

**1. ClauseChunker (절 단위 청킹)**

```python
# src/analysis/chunking/clause_chunker.py
chunker = ClauseChunker()
text = "직원분들이 친절하고 차량 상태도 깨끗했지만 가격이 조금 비쌌어요"
chunks = chunker.chunk(text)
# → ['직원분들이 친절하고', '차량 상태도 깨끗했지만', '가격이 조금 비쌌어요']
```

- 접속사 패턴: 그리고, 하지만, 그런데, 그래서 등
- 연결어미 패턴: -고, -지만, -는데, -어서 등

**2. EmbeddingTagClassifier (임베딩 기반 태그 분류)**

```python
# src/analysis/tags/embedding_classifier.py
classifier = EmbeddingTagClassifier()
tag, score = classifier.classify("친절")
# → ('서비스', 0.534)
```

- 모델: `paraphrase-multilingual-MiniLM-L12-v2`
- 8개 태그 그룹: 서비스, 차량, 가격, 위치/접근성, 편의시설, 반납/픽업, 예약, 여행/관광
- 유사도 임계값: 0.3 (미만이면 '기타')

**3. 파이프라인 통합**

```python
pipeline = BatchPipeline(
    use_chunking=True,        # 절 단위 청킹 활성화
    use_embedding_tags=True   # 임베딩 기반 태그 분류 활성화
)
```

#### 테스트 결과

| 키워드 | 태그 그룹 | 유사도 |
|--------|----------|--------|
| 친절 | 서비스 | 0.534 |
| 깨끗 | 차량 | 0.591 |
| 저렴 | 가격 | 0.755 |
| 공항 | 위치/접근성 | 0.731 |
| 예약 | 예약 | 0.403 |

#### 추가된 파일

```
src/analysis/
├── chunking/
│   ├── __init__.py
│   └── clause_chunker.py
└── tags/
    ├── embedding_classifier.py
    └── tag_embeddings.py
```

#### 의존성
```
sentence-transformers>=2.2.0
```

---

### 2026-01-16: Planning with Files Pattern
- AI 코딩 도구의 컨텍스트 손실 문제 해결
- 3-파일 패턴: task_plan.md, findings.md, progress.md
- Manus 스타트업에서 검증된 패턴
- 출처: https://aisparkup.com/posts/8340

### 2026-01-16: Awesome Claude Skills
- Claude Skills 커뮤니티 컬렉션 (3,000+ stars)
- 출처: https://github.com/VoltAgent/awesome-claude-skills

**주요 카테고리:**
- 문서: docx, pptx, xlsx, pdf
- 디자인: algorithmic-art, canvas-design, frontend-design
- 개발: web-artifacts-builder, mcp-builder, webapp-testing

**참고할만한 기업 Skills:**
- Vercel: React 패턴, 배포 자동화
- Trail of Bits: 보안 분석 (16개 특화 Skills)
- Sentry: 코드 리뷰, PR 생성
- Cloudflare: Workers, KV 가이드

**프로젝트 관련:**
- 컨텍스트 엔지니어링 패턴
- PostgreSQL 쿼리 실행 (Supabase)
- n8n 워크플로우 자동화

---

### 2026-01-16: 리뷰 데이터 가공 및 API 매핑

#### 배경
기존 Excel 데이터(217K 리뷰)를 정제하고 Carmore API로 업체 정보를 매핑

#### 데이터 가공 과정

**1. 원본 데이터 정제**

| 단계 | 작업 | 결과 |
|------|------|------|
| 원본 | 리뷰리스트_20260109.xlsx | 217,660행 × 18열 |
| 빈 리뷰 제거 | 리뷰내용 NULL/빈값 | -33,490 |
| 욕설 제거 | 욕설포함여부='포함' | -236 |
| 블라인드/삭제 제거 | 리뷰상태 필터 | -4,021 |
| **정제 후** | | **180,701행** |

**2. Carmore API 매핑**

```
GET /affiliates?locationType=PARTNERS → 390개 지점
GET /affiliates?locationType=GLOBAL   → 동일 데이터 (중복)
GET /affiliates?locationType=JEJU     → 서버 에러 (500)
```

| 항목 | 값 |
|------|-----|
| API 지점 수 | 390개 |
| Excel 고유 지점 | 1,399개 |
| 매핑 성공 | 353개 (25%) |
| 매핑 실패 | 1,046개 (비활성/폐업 지점) |

**3. 최종 데이터셋**

```
파일: data/리뷰리스트_매핑완료_20260109.xlsx
행 수: 88,624개
지점 수: 353개
컬럼: 리뷰번호, 예약번호, 회사번호, 지점번호, 업체명, 주소, 위치타입, 리뷰내용, 등록일시
```

#### API 제한 사항 발견

**1. 리뷰 API - 매칭 키 없음**
```json
// GET /reviews/{branchId} 응답
{
  "companyName": "고고렌트카",
  "branchName": "전라광주점",
  "opinion": "리뷰내용",
  "createdAt": "2025-04-22T06:56:40.000Z",
  "reservation": {
    "carModel": "모닝 3세대 F/L"  // ← 차종 정보 있음!
  }
  // ❌ 리뷰번호 없음
  // ❌ 예약번호 없음
}
```

**2. 예약 API - 조회 불가**
```
GET /reservation/{reservKey}     → 500 에러
GET /v2/reservations/{id}        → RESERVATION_NOT_FOUND
```
- 완료된 예약은 조회 불가
- Excel 예약번호와 API 예약키 형식 불일치 가능

**3. 제휴사 API - JEJU 타입 에러**
```
GET /affiliates?locationType=JEJU → 500 에러 (서버 문제)
GET /affiliates/{id} 개별 조회    → 500 에러
GET /admin/branch/master         → 401 인증 필요
```

#### 결론

| 목표 | 가능 여부 | 방법 |
|------|----------|------|
| 업체명/주소 매핑 | ✅ 부분 가능 | `/affiliates` API (49% 매핑률) |
| 차종 정보 매핑 | ❌ 불가 | Excel↔API 매칭 키 없음 |
| 전체 지점 정보 | ❌ 불가 | JEJU API 에러, 비활성 지점 미제공 |

#### 향후 차종 정보 획득 방안

API 기반 신규 리뷰 수집 시에만 차종 정보 획득 가능:
```python
# 리뷰 API에서 직접 수집
reviews = api.get_reviews(branch_id)
for review in reviews:
    car_model = review['reservation']['carModel']  # ✅ 가능
```

---

## Useful References

- [PIPELINE.md](/PIPELINE.md) - 파이프라인 상세 문서
- [CLAUDE.md](/CLAUDE.md) - 프로젝트 컨텍스트
- [CARMORE_API.md](/docs/CARMORE_API.md) - API 문서
