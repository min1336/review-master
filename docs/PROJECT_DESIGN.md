# Review Summary AI - 프로젝트 설계 문서

## 1. 시스템 개요

Carmore 렌터카 회사의 리뷰 요약 시스템. 고객 리뷰를 분석하여 지점별 인사이트를 제공.

### 핵심 기능
- 리뷰 데이터 정제 및 가공
- 감성 분석 (Lexicon + BERT Hybrid)
- 키워드 추출 (MeCab)
- 태그 분류 (20개 태그)
- LLM 기반 요약 생성 (GPT-4o-mini)
- Supabase 업로드

---

## 2. 데이터 파이프라인

### 2.1 원본 데이터
- **파일**: `data/리뷰리스트_매핑완료_20260109.xlsx`
- **크기**: 88,624행 × 9열

### 2.2 데이터 정제

> **v4.0 변경**: 필터링 단계 제거로 모든 리뷰 처리

| 항목 | 값 |
|------|------|
| 데이터 소스 | 매핑 완료 파일 |
| 전체 리뷰 | 88,624개 |
| 처리 리뷰 | 88,624개 (필터링 없음) |

### 2.3 컬럼 축소
```
18열 → 6열
- 리뷰번호, 예약번호, 회사번호, 지점번호, 리뷰내용, 등록일시
```

### 2.4 API 매핑
- Carmore API로 업체 정보 추가
- **엔드포인트**: `GET /affiliates?locationType=PARTNERS`
- **추가 컬럼**: 업체명, 주소, 위치타입
- **매핑률**: 49% (API에 활성 지점만 존재)

### 2.5 최종 출력
- **파일**: `data/리뷰리스트_매핑완료_20260109.xlsx`
- **크기**: 88,624행 × 9열
- **지점 수**: 353개

---

## 3. 태그 분류 시스템

### 3.1 분류 방식
```
키워드 추출 (MeCab) → 태그 매핑 → 감성 분류 → 태그 생성
```

### 3.2 태그 매핑
| 카테고리 | 키워드 |
|----------|--------|
| 직원 | 직원, 사장, 스탭, 기사, 대표, 사장님 |
| 차량 | 차량, 차, 자동차, 렌트카 |
| 가격 | 가격, 비용, 요금, 금액 |
| 편의 | 편리, 편의, 이용 |
| 위치 | 위치, 접근성, 주차, 거리 |
| 청결 | 깨끗, 청결, 깔끔, 상태, 컨디션 |
| 시간 | 시간, 대기, 기다 |
| 응대 | 설명, 안내, 상담, 응대 |
| 픽업반납 | 픽업, 반납, 딜리버리, 배달, 인수 |
| 서비스 | 서비스, 추천, 만족 |

### 3.3 감성 키워드
```python
POSITIVE_KW = {'친절', '좋', '깨끗', '편리', '편하', '빠르', '저렴', '만족',
               '추천', '감사', '최고', '깔끔', '쾌적', '넓', '새', '안전',
               '정확', '신속', '쉬운', '훌륭', '좋아'}

NEGATIVE_KW = {'불친절', '더럽', '나쁘', '불편', '느리', '비싸', '불만',
               '별로', '최악', '싫', '실망', '좁', '낡', '지저분', '불쾌',
               '늦', '어렵', '힘들'}
```

### 3.4 최종 태그 (20개)
```
긍정 (10개): 직원_P, 차량_P, 가격_P, 편의_P, 위치_P, 청결_P, 시간_P, 응대_P, 픽업반납_P, 서비스_P
부정 (10개): 직원_N, 차량_N, 가격_N, 편의_N, 위치_N, 청결_N, 시간_N, 응대_N, 픽업반납_N, 서비스_N
```

### 3.5 태그 통계
| 태그 | 긍정(P) | 부정(N) |
|------|---------|---------|
| 청결 | 36,420 | 2,457 |
| 차량 | 30,566 | 2,942 |
| 직원 | 17,268 | 1,348 |
| 서비스 | 11,955 | 991 |
| 픽업반납 | 10,696 | 2,058 |
| 응대 | 9,685 | 1,039 |
| 가격 | 3,494 | 572 |
| 편의 | 2,660 | 203 |
| 위치 | 1,118 | 285 |
| 시간 | 105 | 31 |

---

## 4. API 연동

### 4.1 Carmore API
- **Base URL**: `https://dev-rentcar-api.carmore.kr`
- **문서**: `docs/CARMORE_API.md`

### 4.2 사용 엔드포인트
| 엔드포인트 | 용도 |
|------------|------|
| `GET /affiliates` | 제휴사 목록 조회 |
| `GET /reviews/{branchId}` | 지점별 리뷰 조회 |

### 4.3 제한사항
- JEJU locationType: 500 서버 에러
- 개별 지점 조회: 500 서버 에러
- 관리자 API: 401 인증 필요
- 리뷰 API에 리뷰번호/예약번호 없음 → Excel 매칭 불가

---

## 5. 파이프라인 설계 (v4.0)

### 5.1 현재 구조 (5단계)
```
src/pipeline/batch_pipeline.py

Step 1: Load 매핑완료 Excel (88,624건)
Step 2: Sentiment Analysis (Lexicon + BERT)
Step 3: Keyword Extraction (MeCab) - 옵션: 청킹
Step 4: Aggregate + LLM Summarization (2:1 ratio) - 옵션: 임베딩 태그
Step 5: Export (Excel + Supabase)
```

### 5.2 파이프라인 옵션
```python
pipeline = BatchPipeline(
    use_chunking=True,         # 절 단위 청킹
    use_embedding_tags=True    # 임베딩 기반 태그 분류
)
```

---

## 6. 스케줄러 설계

### 6.1 현재 상태
- Flask-APScheduler 기반
- 매일 02:00 전체 재처리

### 6.2 개선 설계 (예정)
1. **API 리뷰 수집**: 신규 리뷰만 수집
2. **지점별 업데이트**: 신규 리뷰 있는 지점만 재분석
3. **시기별 우선순위**: 최근 리뷰 가중치 적용

---

## 7. 출력 파일

| 파일 | 내용 |
|------|------|
| `data/리뷰리스트_매핑완료_20260109.xlsx` | 정제된 리뷰 데이터 (88,624행) |
| `data/리뷰_태그분류.xlsx` | 태그 분류 결과 |
| `data/지점별_태그집계.xlsx` | 지점별 태그 통계 (351개 지점) |
| `output/summaries.xlsx` | 생성된 요약문 |

---

## 8. 기술 스택

| 구분 | 기술 |
|------|------|
| Backend | Python 3.x, Flask |
| NLP | MeCab (한국어 형태소 분석) |
| Sentiment | BERT + Lexicon Hybrid |
| LLM | OpenAI GPT-4o-mini |
| Database | Supabase (PostgreSQL) |
| Data | pandas, openpyxl |

---

## 9. 주요 상수

```python
MIN_REVIEWS_PER_BRANCH = 30      # 지점당 최소 리뷰 수
MIN_REVIEW_LENGTH = 5           # 최소 리뷰 길이
SENTIMENT_THRESHOLD = 0.45      # 긍정 판정 임계값
LEXICON_HIGH = 0.7              # 확실한 긍정
LEXICON_LOW = 0.3               # 확실한 부정
OPENAI_RPM = 3500               # 분당 요청 제한
MAX_REVIEWS_PER_BRANCH = 30     # 저장할 최근 리뷰 수
```

---

## 10. 디렉토리 구조

```
Review_Summary_AI/
├── src/
│   ├── analysis/
│   │   ├── sentiment/    # Lexicon, BERT, Hybrid
│   │   └── keywords/     # MeCab 추출, 집계
│   ├── api/              # Carmore API 클라이언트
│   ├── config/           # Settings, stopwords
│   ├── llm/              # OpenAI provider
│   ├── pipeline/         # Batch processing
│   ├── db/               # Database connectivity
│   └── preprocessing/    # Data cleaning
├── scripts/              # 실행 스크립트
├── web/                  # Flask API + dashboard
├── data/                 # 입력 Excel 파일
├── output/               # 생성된 결과
└── docs/                 # 문서
```

---

*Last Updated: 2026-01-19 (v4.0 파이프라인 업데이트)*

