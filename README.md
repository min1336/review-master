# Review Summary AI - 전체 프로세스

## 1. 시스템 개요

렌터카 리뷰 데이터를 분석하여 지점별 AI 요약을 생성하고, 운영팀이 검토/승인/게시할 수 있는 대시보드를 제공하는 시스템입니다.

---

## 2. 아키텍처

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Excel 데이터   │ ──▶ │   파이프라인     │ ──▶ │    Supabase     │
│  (8만개 리뷰)   │     │ (BatchPipeline) │     │   (PostgreSQL)  │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
                        ┌─────────────────┐     ┌─────────────────┐
                        │   운영팀 대시보드 │ ◀── │   Flask 서버    │
                        │  (localhost:5000)│     │   (app.py)      │
                        └─────────────────┘     └─────────────────┘
```

---

## 3. 파이프라인 프로세스 (v5.0)

> **v5.0**: 감정분석 제거, 키워드별 감정 판단으로 대체 (6배 속도 향상)

### Step 1: 데이터 로드
- 매핑 완료된 Excel 파일에서 리뷰 로드 (필터링 없음)

### Step 2: 키워드 추출 (청킹 + MeCab)
- 절 단위 청킹 (접속사/연결어미 기준)
- 명사(NNG, NNP) + 형용사(VA) 추출
- 불용어 제거

### Step 3: 태그+감정 분류 + AI 요약 생성
- **임베딩 분류**: BERT 임베딩 + 코사인 유사도로 8개 태그 그룹 분류
- **감정 판단**: 키워드별 규칙 패턴 매칭 (긍정/부정)
- **키워드 집계**: 가중치 적용하여 지점별 TOP 10 키워드
- **LLM 요약**: GPT-4o-mini로 3문장 요약 (태그별 감정 정보 활용)

### Step 4: 결과 저장
- Supabase DB 저장 (요약, 태그, 키워드 매핑)


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

### 스케줄러 설정 (데이터 분석 기반)

| 시즌 | 주기 | 월 | 일평균 리뷰 |
|------|------|-----|------------|
| 성수기 | 주 1회 (일요일) | 6~8월 | 113건 |
| 환절기 | 격주 (1일, 15일) | 3~5, 9~10월 | 95건 |
| 비수기 | 월 1회 (1일) | 11~2월 | 80건 |

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
python -c "from src.pipeline import BatchPipeline; BatchPipeline().run('data/리뷰리스트_매핑완료_20260109.xlsx')"

# Flask 서버 실행
python web/app.py
```

---

## 8. 처리 결과 요약 (v5.0)

| 항목 | 값 |
|------|-----|
| 데이터 소스 | 리뷰리스트_매핑완료_20260109.xlsx |
| 전체 리뷰 | 88,624개 |
| 처리 지점 | 353개 |
| 소요 시간 | ~56초 |

> **v5.0 변경**: 감정분석 제거로 6배 속도 향상 (320초 → 56초)

