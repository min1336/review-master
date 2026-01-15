# 작업 일지 - 2026년 1월 14일

## 개요
Review Summary AI 프로젝트의 코드 정리, Supabase 통합, API 키 문제 해결 작업 진행

---

## 1. 파이프라인 코드 정리

### 1.1 사용하지 않는 파일 삭제
프로젝트 내 불필요한 파일들을 정리하여 **47개 → 17개**로 축소

#### 삭제된 파일 목록

| 분류 | 삭제 파일 |
|------|----------|
| **중복 스크립트** | `run_production.py`, `run_new_pipeline.py`, `scripts/test_top3.py` |
| **쉘 스크립트** | `scripts/run*.sh` |
| **미사용 소스** | `src/keyword_extractor.py`, `src/summary_generator.py`, `src/sentiment_analyzer.py`, `src/review_processor.py` |
| **분석 폴더** | `analysis/` (전체) |
| **캐시/결과** | `cache/`, `results/` (전체) |
| **테스트** | `tests/` (전체) |
| **문서** | `docs/` (전체) |
| **시각화** | `visualizations/` (전체) |
| **이전 템플릿** | `web/templates/index.html`, `monitor.html`, `results.html` |

### 1.2 현재 프로젝트 구조
```
Review_Summary_AI/
├── scripts/
│   └── pipeline_v3.py      # 메인 파이프라인
├── web/
│   ├── app.py              # Flask API 서버
│   ├── supabase_client.py  # Supabase 연동
│   └── templates/
│       └── dashboard.html  # 운영팀 대시보드
├── output/                 # 결과 저장 폴더
├── .env                    # 환경변수
└── requirements.txt        # 의존성
```

---

## 2. Pipeline → Supabase 직접 통합

### 2.1 구현 내용
파이프라인 실행 결과가 자동으로 Supabase에 저장되도록 통합

#### supabase_client.py 추가 함수

```python
def upsert_summary(branch_id: int, ai_summary: str, keywords: list, review_count: int):
    """파이프라인에서 요약 결과 저장/업데이트"""
    # 1. branches 테이블 upsert
    # 2. summaries 테이블 update 또는 insert

def upsert_summaries_batch(summaries: list):
    """여러 요약 결과를 일괄 저장"""
```

#### pipeline_v3.py 수정 사항

1. `.env` 경로 수정 (상대경로 → 절대경로)
```python
from pathlib import Path
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)
```

2. Supabase 저장 로직 추가 (Step 9)
```python
if SUPABASE_AVAILABLE:
    print("[Step 9] Supabase 저장")
    saved = upsert_summaries_batch(supabase_data)
    print(f"✅ Supabase 저장 완료: {saved}개 지점")
```

### 2.2 결과
- **371개 지점** 데이터가 Supabase에 성공적으로 마이그레이션됨
- 파이프라인 실행 시 자동으로 DB 업데이트

---

## 3. Gemini API 키 문제 해결

### 3.1 문제 상황
- 파이프라인 실행 시 API 키를 찾지 못하는 오류 발생
- 개별 테스트는 성공하나 전체 파이프라인에서 실패

### 3.2 시도한 해결 방법

| 시도 | 내용 | 결과 |
|------|------|------|
| 1 | `.env` 경로를 절대경로로 수정 (pipeline_v3.py) | 부분 해결 |
| 2 | supabase_client.py의 `.env` 경로도 수정 | 부분 해결 |
| 3 | 매 호출마다 `genai.configure()` 실행 | 테스트 성공, 파이프라인 실패 |
| 4 | 매 호출마다 새 모델 인스턴스 생성 | 테스트 성공, 파이프라인 실패 |

### 3.3 현재 코드 (pipeline_v3.py)
```python
# 매 호출마다 새로운 모델 인스턴스 생성
genai.configure(api_key=self.gemini_api_key)
model = genai.GenerativeModel('gemini-2.5-flash-lite')
response = model.generate_content(prompt)
```

### 3.4 상태
- **테스트 스크립트**: 정상 동작
- **전체 파이프라인**: fallback 메시지 출력 (API 호출 실패)
- **다음 단계**: 하드코딩 방식 검토 필요

---

## 4. 환경변수 업데이트

### .env 파일 내용
```
GEMINI_API_KEY=your-gemini-api-key
SUPABASE_URL=your-supabase-url
SUPABASE_KEY=your-supabase-key
```

---

## 5. 아키텍처 다이어그램 작성

파이프라인 구조를 시각화한 아키텍처 다이어그램 작성

### 파이프라인 9단계 흐름
```
Excel 입력
    │
    ▼
┌─────────────────────────────────┐
│ Step 1-4: 전처리                │
│ 로드 → 필터링 → 정제 → 그룹화  │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ Step 5-6: 분석                  │
│ 감정분석(Hybrid) + 키워드(MeCab)│
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ Step 7-8: AI 생성               │
│ Gemini 요약 + Top3 리뷰 선정   │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ Step 9: 저장                    │
│ Excel + Supabase               │
└─────────────────────────────────┘
    │
    ▼
운영팀 대시보드 (Flask)
```

---

## 6. 남은 작업 (TODO)

| 우선순위 | 작업 | 상태 |
|----------|------|------|
| **높음** | Gemini API 키 문제 완전 해결 | 🔄 진행중 |
| 중간 | Phase 4: 스케줄러 구현 | ⏳ 대기 |
| 낮음 | Phase 5: 외부 API 연동 | ⏳ 대기 |

---

## 7. 기술 스택 요약

| 영역 | 기술 |
|------|------|
| 전처리 | Pandas, OpenPyXL |
| 감정분석 | Lexicon (1차) + BERT (2차) |
| 키워드 | MeCab + TF-IDF |
| AI 요약 | Google Gemini 2.5 Flash Lite |
| 데이터베이스 | Supabase (PostgreSQL) |
| 백엔드 | Flask |
| 프론트엔드 | HTML + JavaScript (Vanilla) |

---

## 8. 접속 정보

- **대시보드**: http://localhost:5000
- **API 엔드포인트**:
  - `GET /api/summaries` - 전체 목록
  - `GET /api/summaries/<id>` - 상세 조회
  - `PUT /api/summaries/<id>` - 수정
  - `POST /api/summaries/<id>/approve` - 승인
  - `POST /api/summaries/<id>/publish` - 게시
  - `GET /api/stats` - 통계

---

*작성일: 2026-01-14*
