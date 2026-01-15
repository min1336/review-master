# Review Summary AI - 전체 프로세스

## 1. 시스템 개요

렌터카 리뷰 데이터를 분석하여 지점별 AI 요약을 생성하고, 운영팀이 검토/승인/게시할 수 있는 대시보드를 제공하는 시스템입니다.

---

## 2. 아키텍처

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Excel 데이터   │ ──▶ │   파이프라인     │ ──▶ │    Supabase     │
│  (21만개 리뷰)   │     │   (pipeline_v3) │     │   (PostgreSQL)  │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
                        ┌─────────────────┐     ┌─────────────────┐
                        │   운영팀 대시보드 │ ◀── │   Flask 서버    │
                        │  (localhost:5000)│     │   (app.py)      │
                        └─────────────────┘     └─────────────────┘
```

---

## 3. 파이프라인 프로세스 (pipeline_v3.py)

### Step 1: 데이터 로드
- Excel 파일에서 21만개 리뷰 로드

### Step 2: 빈 리뷰 제거
- null, 빈 문자열, 5자 미만 리뷰 제거
- 결과: 184,070개

### Step 3: 블라인드/삭제 제거 + 지점 필터링
- 블라인드/삭제 상태 리뷰 제거
- 30개 이하 리뷰 지점 제외
- 결과: 371개 지점, 175,682개 리뷰

### Step 4: 2단계 하이브리드 감정 분석
```
┌────────────────┐
│  리뷰 텍스트    │
└───────┬────────┘
        ▼
┌────────────────┐     확실한 긍정/부정
│ 1차: Lexicon   │ ──────────────────▶ 결과 반환
│ (사전 기반)     │
└───────┬────────┘
        │ 애매한 경우 (0.3~0.7)
        ▼
┌────────────────┐
│ 2차: BERT      │ ──────────────────▶ 결과 반환
│ (딥러닝)        │
└────────────────┘
```

### Step 5: 긍정 리뷰 필터링
- sentiment_score >= 0.45인 긍정 리뷰만 선별
- 결과: 130,516개 (74.3%)

### Step 6: 키워드 추출 (MeCab)
- 명사(NNG, NNP) + 형용사(VA) 추출
- 불용어 제거
- 가중치 적용하여 지점별 TOP 10 키워드 선정

### Step 7: AI 요약 생성
- **LLM**: OpenAI GPT-4o-mini
- **입력**: TOP 10 키워드 + 대표 리뷰 5개
- **Rate Limit**: 500 RPM

### Step 8: 결과 저장
- Excel 출력: `output/branch_summaries.xlsx`
- Supabase DB 저장: 371개 지점

---

## 4. 데이터베이스 구조 (Supabase)

| 테이블 | 설명 |
|--------|------|
| `branches` | 지점 정보 |
| `summaries` | AI 요약 결과 (status: draft/approved/published) |
| `branch_keywords` | 지점별 키워드 (가중치 포함) |
| `scheduler_config` | 스케줄러 설정 (성수기/일반기/비수기) |
| `scheduler_logs` | 실행 로그 |

---

## 5. 운영 대시보드 (Flask)

### 접속 URL
- http://localhost:5000

### API 엔드포인트

| 메소드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/summaries` | 전체 목록 |
| GET | `/api/summaries/<id>` | 상세 조회 |
| PUT | `/api/summaries/<id>` | 수정 |
| POST | `/api/summaries/<id>/approve` | 승인 |
| POST | `/api/summaries/<id>/publish` | 게시 |
| GET | `/api/stats` | 통계 |
| GET | `/api/scheduler/status` | 스케줄러 상태 |
| POST | `/api/scheduler/trigger` | 수동 실행 |

### 스케줄러 설정

| 시즌 | 주기 | 월 |
|------|------|-----|
| 성수기 | 매일 새벽 3시 | 7, 8, 12월 |
| 일반기 | 주 3회 (월/수/금) | 3~6, 9~11월 |
| 비수기 | 주 1회 (월) | 1, 2월 |

---

## 6. 환경 설정

### .env 파일
```env
# OpenAI
OPENAI_API_KEY=sk-...

# Supabase (service_role 키 사용)
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...

# LLM Provider
LLM_PROVIDER=openai
```

---

## 7. 실행 방법

```bash
# 가상환경 활성화
source venv/bin/activate

# 파이프라인 실행
python scripts/pipeline_v3.py

# Flask 서버 실행
python web/app.py
```

---

## 8. 처리 결과 요약

| 항목 | 값 |
|------|-----|
| 전체 리뷰 | 217,660개 |
| 처리 리뷰 | 175,682개 |
| 긍정 리뷰 | 130,516개 (74.3%) |
| 중립 | 40,003개 (22.8%) |
| 부정 | 5,163개 (2.9%) |
| 처리 지점 | 371개 |
| 소요 시간 | ~143초 |
