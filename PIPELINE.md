# Review Summary AI - 파이프라인 상세 문서

## 1. 시스템 개요

> **v5.0**: 감정분석 제거, 키워드별 감정 판단으로 대체 (6배 속도 향상)

카모아 렌터카 리뷰를 분석하여 지점별 AI 요약을 생성하는 시스템

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Excel      │     │  Pipeline    │     │  Supabase    │
│  리뷰 데이터  │ ──▶ │   v5.0       │ ──▶ │  PostgreSQL  │
│  (매핑완료)   │     │  (4단계)     │     │              │
└──────────────┘     └──────────────┘     └──────────────┘
```

---

## 2. 파이프라인 4단계

### Step 1: 데이터 로드
```python
df = pd.read_excel('data/리뷰리스트_매핑완료_20260109.xlsx')
# 필터링 없이 모든 리뷰 처리
```

### Step 2: 키워드 추출 (청킹 + MeCab)

```
입력: "직원분들이 정말 친절하고 차량도 깨끗했어요"
         │
         ▼
┌─────────────────────────┐
│   절 단위 청킹            │
│   ClauseChunker         │
│   접속사/연결어미 기준    │
└─────────────────────────┘
         │
         ▼
청크: ['직원분들이 친절하고', '차량도 깨끗했어요']
         │
         ▼
┌─────────────────────────┐
│   MeCab 형태소 분석      │
│   - 명사 (NNG, NNP)      │
│   - 형용사 (VA)          │
└─────────────────────────┘
         │
         ▼
┌─────────────────────────┐
│   불용어 제거 (70개)     │
└─────────────────────────┘
         │
         ▼
출력: ['직원', '친절', '차량', '깨끗']
```

### Step 3: 태그+감정 분류 + 키워드 집계 + AI 요약 생성

#### 3-1. 태그+감정 분류 (임베딩 기반)
```
키워드: ['친절', '깨끗', '저렴', '냄새']
         │
         ▼
┌─────────────────────────────────────────┐
│   EmbeddingTagClassifier                 │
│   모델: paraphrase-multilingual-MiniLM   │
│   BERT 임베딩 + 코사인 유사도             │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│   8개 태그 그룹 분류                      │
│   서비스/차량/가격/위치/편의시설/         │
│   반납픽업/예약/여행관광                  │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│   감정 판단 (규칙 패턴 매칭)              │
│   부정: 불친절, 비싸, 냄새, 아쉬운 등     │
└─────────────────────────────────────────┘
         │
         ▼
결과: 친절→서비스(긍정), 깨끗→차량(긍정),
      저렴→가격(긍정), 냄새→차량(부정)
```

#### 3-2. 지점별 키워드 집계 (가중치)

| 요소 | 가중치 |
|------|--------|
| 최신성 | 1개월 이내: 2.0x, 1년 이상: 0.3x |
| 공감수 | 10+: 2.5x, 5+: 1.8x |
| 리뷰 길이 | 100자+: 1.5x, 20자-: 0.3x |
| 별점 | 4.5+: 1.2x, 3.0-: 0.2x |

**출력:** 지점별 TOP 10 키워드

#### 3-3. AI 요약 생성

**대표 리뷰 선택:**
```python
# 키워드 포함 많은 순 5개 선택
top_reviews = branch_df.nlargest(5, 'kw_count')['리뷰내용'].tolist()
```

**태그별 감정 데이터 활용:**
```
<tag_sentiment_analysis>
[서비스] / 긍정: 친절, 응대, 설명 / 부정: 불친절
[차량] / 긍정: 깨끗, 신차, 청결 / 부정: 냄새
[가격] / 긍정: 저렴, 가성비 / 부정: 비싸
</tag_sentiment_analysis>
```

**프롬프트:**
```
## 역할 (Role)
당신은 '카모아'의 전문 리뷰 분석가이자, 고객의 현명한 선택을 돕는 쇼핑 어시스턴트입니다. 
방대한 고객 리뷰 데이터를 분석하여, 예비 고객이 상품(차량/업체)의 특징을 한눈에 파악할 수 있도록 핵심 정보를 요약하는 것이 당신의 임무입니다.

## 분석 지침 (Guidelines)

1. **한 줄 요약 (One-Line Summary)**
   - 목표: 상품의 핵심 가치를 가장 직관적으로 전달합니다.
   - 형식: "~하기 좋은", "~가 특징인" 등 수식어를 활용하여 30자 이내의 완결된 문장으로 작성하세요.
   - 예시: "깨끗한 차량 관리와 친절한 응대로 가족 여행에 추천하는 차량입니다."

2. **긍정 리뷰 요약 (Pros)**
   - 고객들이 공통적으로 칭찬하는 포인트(청결도, 옵션, 픽업 편의성 등)를 3가지 내외로 통합하여 자연스러운 문장으로 요약하세요.
   - 톤앤매너: 신뢰감 있고 부드러운 '해요체'를 사용하세요.

3. **부정 리뷰 요약 (Cons) ** *중요 로직 적용*
   - **[조건 1]** 전체 텍스트 중 부정적인 내용의 비중이 매우 낮거나(약 5% 미만), 사소한 불만(단순 날씨 탓 등)일 경우:
     → 출력 문구: "대부분 긍정적인 리뷰가 많아 아쉬운 점을 찾기 어려워요! 👏"
   - **[조건 2]** 개선점이나 불편 사항이 명확히 존재하는 경우:
     → 비판적인 내용을 순화하여 부드러운 톤으로 전달하되, 사실을 왜곡하지 마세요. (예: "담배 냄새가 난다는 의견이 있어요" → "차량 냄새에 민감하시다면 환기가 필요할 수 있어요.")

4. **주요 키워드 (Top Keywords)**
   - 빈도수가 높은 핵심 단어(형용사+명사 조합 권장)를 최대 5개 추출하여 해시태그(#) 형태로 출력하세요.
   - 예시: #깨끗한실내 #빠른셔틀 #친절한직원 #금연차량 #가성비

5. **감성 분석 (Sentiment Score)**
   - 전체 리뷰의 분위기를 분석하여 긍정 비율을 0~100% 사이의 숫자로 산출하세요.

## 제약 사항 (Constraints)
- 모든 문장은 고객이 읽기 편한 구어체(해요체)를 사용하되, 가벼워 보이지 않도록 정중함을 유지하세요.
- 이모지를 적절히 사용하여 시각적 주목도를 높이세요.
- 없는 내용을 지어내지 마세요 (Hallucination 방지).

## 출력 형식 (Output Format)
반드시 아래 형식을 지켜서 답변하세요.

**[한 줄 요약]**
(내용)

**[👍 이런 점이 좋았어요]**
(내용)

**[🤔 이 점은 참고해주세요]**
(내용)

```

**출력 예시:**
```
이 사과는 씻지 않고도 먹을 수 있어서 편리하고, 건강에 좋아서 많은 사람들이 만족하고 계셨어요. 사과의 당도가 높아서 아삭하고 달콤하며, 껍질과 함께 먹으면 더 맛있다는 의견도 있었어요. 또한, 가격이 합리적이고 상품의 품질도 좋아서 많은 사람들이 만족하고 계셨어요. 다만, 가격이 조금 부담스러운 면도 있었습니다.
```

### Step 4: Supabase 저장

```
┌─────────────────────────────────────────┐
│           Supabase 저장 구조             │
└─────────────────────────────────────────┘

4-1: 요약 저장 (summaries)
     └─ branch_id, ai_summary, keywords, status

4-2: 태그 집계 저장 (branch_tags)
     └─ branch_id, tag_id, count, weighted_score

4-3: 키워드 매핑 저장 (keyword_tag_mappings)
     └─ keyword, tag_id, is_auto
```

---

## 4. 데이터베이스 스키마

### summaries (요약 결과)
```sql
CREATE TABLE summaries (
    id SERIAL PRIMARY KEY,
    branch_id INTEGER UNIQUE,
    ai_summary TEXT,
    edited_summary TEXT,
    keywords JSONB DEFAULT '[]',
    review_count INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'draft'  -- draft/approved/published
);
```

### branch_sentiment_stats (감정 통계)
```sql
CREATE TABLE branch_sentiment_stats (
    id SERIAL PRIMARY KEY,
    branch_id INTEGER UNIQUE,
    positive_count INTEGER DEFAULT 0,
    negative_count INTEGER DEFAULT 0,
    neutral_count INTEGER DEFAULT 0,
    total_count INTEGER DEFAULT 0,
    positive_ratio DECIMAL(5,2),
    negative_ratio DECIMAL(5,2)
);
```

### recent_reviews (최근 리뷰 샘플)
```sql
CREATE TABLE recent_reviews (
    id SERIAL PRIMARY KEY,
    branch_id INTEGER,
    content TEXT,
    sentiment VARCHAR(20),
    sentiment_score DECIMAL(5,4),
    created_at TIMESTAMP DEFAULT NOW()
);

-- 1개월 이전 자동 삭제
CREATE FUNCTION cleanup_old_reviews() ...
```

### branch_keywords (키워드 + 가중치)
```sql
CREATE TABLE branch_keywords (
    branch_id INTEGER,
    keyword VARCHAR(50),
    raw_count INTEGER,
    weighted_score DECIMAL(10,2)
);
```

---

## 5. API 엔드포인트

### 요약 관리
```
GET    /api/summaries              전체 목록
GET    /api/summaries/<id>         상세 조회
PUT    /api/summaries/<id>         수정
POST   /api/summaries/<id>/approve 승인
POST   /api/summaries/<id>/publish 게시
```

### 감정태그 통계
```
GET    /api/sentiment/stats        지점별 감정통계
       ?branch_id=123
GET    /api/sentiment/stats/all    전체 지점 통계 목록
```

### 최근 리뷰
```
GET    /api/reviews/recent         최근 리뷰 검색 (1개월)
       ?sentiment=positive&branch_id=123&limit=100
POST   /api/reviews/cleanup        오래된 리뷰 삭제
       {"days": 30}
```

### 스케줄러
```
GET    /api/scheduler/status       상태 조회
GET    /api/scheduler/config       설정 조회
PUT    /api/scheduler/config/<key> 설정 변경
POST   /api/scheduler/trigger      수동 실행
GET    /api/scheduler/logs         실행 로그
```

---

## 6. 스케줄러 설정

| 시즌 | config_key | cron | 실행 주기 |
|------|------------|------|----------|
| 성수기 | peak_season | `0 3 * * *` | 매일 새벽 3시 |
| 일반기 | normal_season | `0 3 * * 1,3,5` | 월/수/금 새벽 3시 |
| 비수기 | off_season | `0 3 * * 1` | 월요일 새벽 3시 |

---

## 7. 실행 방법

```bash
# 가상환경 활성화
source venv/bin/activate

# 파이프라인 실행
python -c "from src.pipeline import BatchPipeline; BatchPipeline().run('data/리뷰리스트_매핑완료_20260109.xlsx')"

# Flask 서버 실행
python web/app.py
# 접속: http://localhost:5000
```

---

## 8. 환경 변수 (.env)

```env
# LLM Provider
LLM_PROVIDER=openai  # or gemini
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...

# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...
```

---

## 9. 처리 결과 요약 (v5.0)

| 단계 | 입력 | 출력 | 비고 |
|------|------|------|------|
| Step 1: 데이터 로드 | Excel | 88,624 | 매핑 완료 파일 |
| Step 2: 키워드 추출 | 88,624 | ~200K 청크 | 청킹 + MeCab |
| Step 3: 태그+요약 | 키워드 | 지점별 | 임베딩 분류 + LLM |
| Step 4: DB 저장 | 지점별 | 지점별 | Supabase |

### 성능 비교

| 버전 | 감정 분석 | 소요 시간 |
|------|----------|----------|
| v4.0 | Lexicon + BERT | ~320초 |
| v5.0 | 키워드 패턴 | ~56초 |
| **개선** | - | **6배 향상** |

---

## 10. 저장 용량 최적화

| 항목 | 레코드 수 | 예상 용량 |
|------|----------|----------|
| summaries | ~300 | ~1MB |
| branch_keywords | ~3,000 | ~2MB |
| branch_sentiment_stats | ~300 | ~100KB |
| recent_reviews | ~3,000 | ~2MB |
| **합계** | **~6,600** | **~5MB** |

> 전체 리뷰 저장 시 ~300MB → **98% 용량 절약**
