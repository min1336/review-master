# Review Summary AI - 파이프라인 상세 문서

## 1. 시스템 개요

카모아 렌터카 리뷰 217K건을 분석하여 지점별 AI 요약을 생성하는 시스템

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Excel      │     │  Pipeline    │     │  Supabase    │
│  리뷰 데이터  │ ──▶ │   v3.2       │ ──▶ │  PostgreSQL  │
│  (217K건)    │     │              │     │              │
└──────────────┘     └──────────────┘     └──────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │   Flask API  │
                     │   대시보드    │
                     └──────────────┘
```

---

## 2. 파이프라인 9단계

### Step 1: 데이터 로드
```python
df = pd.read_excel('data/리뷰리스트_20260109.xlsx')
# 출력: 217,660개 리뷰
```

### Step 2: 빈 리뷰 제거
| 필터 조건 | 설명 |
|-----------|------|
| `null` | 빈 값 제거 |
| 빈 문자열 | 공백만 있는 리뷰 제거 |
| 5자 미만 | 의미 없는 짧은 리뷰 제거 |

### Step 3: 블라인드/삭제 제거 + 지점 필터링
- 블라인드/삭제 상태 리뷰 제거
- 30개 미만 리뷰 지점 제외

### Step 4: 하이브리드 감정 분석

```
              ┌──────────────┐
              │  리뷰 텍스트  │
              └──────┬───────┘
                     │
                     ▼
        ┌────────────────────────┐
        │   1차: Lexicon 분석     │
        │   (사전 기반, 빠름)      │
        └────────────┬───────────┘
                     │
     ┌───────────────┼───────────────┐
     │               │               │
     ▼               ▼               ▼
┌─────────┐   ┌───────────┐   ┌─────────┐
│score≥0.7│   │ 0.3~0.7   │   │score≤0.3│
│  긍정   │   │   애매함   │   │  부정   │
└─────────┘   └─────┬─────┘   └─────────┘
                    │
                    ▼
          ┌──────────────────┐
          │  2차: BERT 분석   │
          │  (딥러닝, 정밀)   │
          └──────────────────┘
                    │
                    ▼
           positive / neutral / negative
```

**감정 어휘 사전:**
```python
POSITIVE = {'좋다', '최고', '만족', '친절', '깨끗', '추천', '훌륭', '완벽'}
NEGATIVE = {'불친절', '불편', '더럽다', '느리다', '비싸다', '불만', '실망'}
```

### Step 5: 감정 통계 (필터링 없음)

> **변경됨:** 기존에는 긍정 리뷰만 필터링했으나, 현재는 모든 리뷰 유지

```python
# 모든 리뷰 유지 (필터링 없음)
df_filtered = df.copy()

# 통계만 기록
print(f"긍정: {positive_count}개 ({positive_ratio}%)")
print(f"부정: {negative_count}개 ({negative_ratio}%)")
print(f"중립: {neutral_count}개 ({neutral_ratio}%)")
```

### Step 6: 키워드 추출 (MeCab)

```
입력: "직원분들이 정말 친절하고 차량도 깨끗했어요"
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

### Step 7: 지점별 키워드 집계 (가중치)

| 요소 | 가중치 |
|------|--------|
| 최신성 | 1개월 이내: 2.0x, 1년 이상: 0.3x |
| 공감수 | 10+: 2.5x, 5+: 1.8x |
| 리뷰 길이 | 100자+: 1.5x, 20자-: 0.3x |
| 별점 | 4.5+: 1.2x, 3.0-: 0.2x |

**출력:** 지점별 TOP 10 키워드

### Step 8: AI 요약 생성 (2:1 비율)

> **변경됨:** 긍정 2줄 + 아쉬운 점 1줄 = 신뢰도 향상

**대표 리뷰 선택:**
```python
# 긍정 리뷰 3개 + 부정 리뷰 2개 = 균형 잡힌 샘플
positive_reviews = df[df['sentiment'] == 'positive'].head(3)
negative_reviews = df[df['sentiment'] == 'negative'].head(2)
```

**프롬프트:**
```
당신은 20년차 베테랑 프리미엄 렌터카 카모아 마케터입니다.

가이드라인:
1. 핵심 키워드를 자연스럽게 녹여내세요.
2. 전문적인 어조를 사용하세요.
3. 반드시 3줄로 작성: 긍정 2줄 + 아쉬운 점 1줄 (2:1 비율)
4. 아쉬운 점은 부드럽게 표현 (예: "다소 아쉬운 점은...")
5. 마크다운, 이모지 없이 순수 텍스트만
```

**출력 예시:**
```
친절하고 신속한 서비스로 고객 만족도가 높습니다.
차량 상태가 깨끗하고 가격 대비 가성비가 뛰어납니다.
다소 아쉬운 점은 일부 이용객이 픽업 시 대기 시간이 길다고 느꼈습니다.
```

### Step 9: Supabase 저장

```
┌─────────────────────────────────────────┐
│           Supabase 저장 구조             │
└─────────────────────────────────────────┘

9-1: 요약 저장 (summaries)
     └─ branch_id, ai_summary, keywords, status

9-2: 감정통계 저장 (branch_sentiment_stats)
     └─ branch_id, positive_count, negative_count, neutral_count, ratio

9-3: 최근 리뷰 샘플 저장 (recent_reviews)
     └─ 지점당 최근 10개만 (1개월 후 자동 삭제)
```

---

## 3. 데이터베이스 스키마

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

## 4. API 엔드포인트

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

## 5. 스케줄러 설정

| 시즌 | config_key | cron | 실행 주기 |
|------|------------|------|----------|
| 성수기 | peak_season | `0 3 * * *` | 매일 새벽 3시 |
| 일반기 | normal_season | `0 3 * * 1,3,5` | 월/수/금 새벽 3시 |
| 비수기 | off_season | `0 3 * * 1` | 월요일 새벽 3시 |

---

## 6. 실행 방법

```bash
# 가상환경 활성화
source venv/bin/activate

# 파이프라인 실행
python scripts/pipeline_v3.py

# Flask 서버 실행
python web/app.py
# 접속: http://localhost:5000
```

---

## 7. 환경 변수 (.env)

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

## 8. 처리 결과 요약

| 단계 | 입력 | 출력 | 비고 |
|------|------|------|------|
| 로드 | Excel | 217,660 | - |
| 빈 리뷰 제거 | 217,660 | 184,070 | -33,590 |
| 블라인드/삭제 | 184,070 | 175,682 | -8,388 |
| 감정 분석 | 175,682 | 175,682 | 태그만 부여 |
| 필터링 | - | - | **없음 (전체 유지)** |
| 키워드 추출 | 175,682 | 371 지점 | TOP 10 |
| AI 요약 | 371 | 371 | 2:1 비율 |
| DB 저장 | 371 | 371 | 통계 + 샘플 |

---

## 9. 저장 용량 최적화

| 항목 | 레코드 수 | 예상 용량 |
|------|----------|----------|
| summaries | ~300 | ~1MB |
| branch_keywords | ~3,000 | ~2MB |
| branch_sentiment_stats | ~300 | ~100KB |
| recent_reviews | ~3,000 | ~2MB |
| **합계** | **~6,600** | **~5MB** |

> 전체 리뷰 저장 시 ~300MB → **98% 용량 절약**
