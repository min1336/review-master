# 변경 이력 - 2026년 1월 20일

## 개요

프롬프트 v8 개선 (별점 기반 감정비율), 지점명 DB 업데이트, 파이프라인 실행 시도

---

## 1. 프롬프트 v8 개선: 별점 기반 감정비율

### 수정 파일
- `src/llm/prompts.py`
- `src/pipeline/batch_pipeline.py`

### 1.1 감정비율 계산 방식 변경

**이전 (키워드 기반)**
```python
# 키워드별 감정 태그로 긍정/부정 집계
positive_count = sum(1 for kw in keywords if kw.sentiment == 'positive')
negative_count = sum(1 for kw in keywords if kw.sentiment == 'negative')
```

**현재 (별점 기반)**
```python
# 리뷰 별점으로 긍정/부정 집계
# 3-5점: 긍정, 1-2점: 부정
positive_count = len(df[(df['평균평점'] >= 3)])
negative_count = len(df[(df['평균평점'] < 3)])
```

### 1.2 새 헬퍼 함수 추가

`batch_pipeline.py`에 `_calculate_sentiment_stats()` 함수 추가:

```python
def _calculate_sentiment_stats(self, df: pd.DataFrame) -> dict:
    """별점 기반 감정 통계 계산

    Args:
        df: 리뷰 데이터프레임 (평균평점 컬럼 필요)

    Returns:
        {'positive_ratio': float, 'negative_ratio': float,
         'positive_count': int, 'negative_count': int}
    """
    positive = len(df[df['평균평점'] >= 3])
    negative = len(df[df['평균평점'] < 3])
    total = positive + negative

    return {
        'positive_ratio': round(positive / total * 100) if total > 0 else 0,
        'negative_ratio': round(negative / total * 100) if total > 0 else 0,
        'positive_count': positive,
        'negative_count': negative
    }
```

### 1.3 프롬프트 출력 형식 변경

**이전 형식**
```
[긍정 키워드]: 친절, 깨끗, 편리
[부정 키워드]: 비싸, 냄새
```

**현재 형식 (v8)**
```
[긍정 85% / 부정 15%]

자연스러운 문단 형식의 요약...

다만, 일부 고객은 가격에 대한 아쉬움을 표현했습니다.
```

### 1.4 프롬프트 분기 로직

| 조건 | 출력 형식 |
|-----|----------|
| 부정 없음 + 통계 있음 | `[긍정 N%]` + 긍정 요약만 |
| 부정 있음 + 통계 있음 | `[긍정 N% / 부정 N%]` + 긍정 요약 + "다만, ~" |
| 부정 없음 + 통계 없음 | 긍정 요약만 |
| 부정 있음 + 통계 없음 | 긍정 요약 + "다만, ~" |

---

## 2. 지점명 DB 업데이트

### 작업 내용
- Supabase `branch_summaries` 테이블의 지점명 업데이트
- 데이터 소스: `data/리뷰_예약통합.xlsx`의 `예약_지점명` 컬럼

### 업데이트 결과

| 항목 | 수량 |
|-----|-----|
| DB 전체 지점 | 404개 |
| 이름 없는 지점 (업데이트 전) | 33개 |
| 업데이트 완료 | 400개 |

### 업데이트 쿼리
```sql
UPDATE branch_summaries
SET branch_name = '예약_지점명',
    review_count = (해당 지점 리뷰 수)
WHERE branch_id = N;
```

---

## 3. 파이프라인 구조 탐색

### 3.1 파이프라인 v5.0 단계

| Step | 내용 | 설명 |
|------|------|------|
| 1 | 데이터 로드 | Excel에서 리뷰 데이터 로드 |
| 2 | 키워드 추출 | MeCab 형태소 분석 + 청킹 |
| 3 | 태그 분류 + AI 요약 | 임베딩 기반 태그 분류, LLM 요약 생성 |
| 4 | DB 저장 | Supabase에 결과 저장 |

### 3.2 태그 분류 시스템

**9개 태그 카테고리:**
1. 고객응대
2. 차량외관
3. 차량청결
4. 가성비
5. 위치/접근성
6. 서비스
7. 반납/픽업
8. 배차/시간
9. 보험/보장

**분류 방식:**
1. **규칙 기반 매핑** (우선 적용): 도메인 키워드 → 태그
2. **임베딩 기반 분류**: Sentence-Transformers 코사인 유사도 (threshold: 0.3)

### 3.3 프롬프트-태그 연결

```python
# 프롬프트 생성 시 태그별 감정 데이터 전달
prompt = PromptTemplates.generate_summary_prompt(
    keywords=top_keywords,           # TOP-N 키워드
    tag_sentiments=tag_sentiments,   # {태그: {긍정: N, 부정: N}}
    summary_stats=sentiment_stats    # {긍정비율, 부정비율}
)
```

---

## 4. 파이프라인 실행 시도

### 4.1 목표
`data/리뷰_예약통합.xlsx` 전체 파이프라인 실행 (AI 요약 생략)

### 4.2 데이터 규모

| 항목 | 수량 |
|-----|-----|
| 총 리뷰 | 181,615개 |
| 총 지점 | 1,408개 |
| 리뷰 30건 이상 지점 | 378개 |

### 4.3 실행 코드

```python
from src.pipeline import BatchPipeline

# AI 요약 강제 비활성화
p = BatchPipeline()
p.llm_provider = None  # 초기화 후 강제 설정

p.run('data/리뷰_예약통합.xlsx')
```

### 4.4 발견된 이슈

**`llm_provider=None` 파라미터 버그:**

```python
# BatchPipeline.__init__()
if llm_provider:                    # None은 False로 평가
    self.llm_provider = llm_provider
elif settings.llm_provider == 'openai':
    self.llm_provider = OpenAIProvider(...)  # 기본 프로바이더 생성됨
```

**해결 방법:**
```python
p = BatchPipeline()
p.llm_provider = None  # 초기화 후 강제로 None 설정
```

### 4.5 실행 결과

| 단계 | 상태 | 비고 |
|-----|------|-----|
| Step 1: 데이터 로드 | 완료 | 181,615개 리뷰, 1,408개 지점 |
| Step 2: 키워드 추출 | 진행 중 중단 | 약 30분 실행 후 사용자 요청으로 중단 |
| Step 3: 태그 분류 | 미실행 | - |
| Step 4: DB 저장 | 미실행 | - |

**중단 사유:** 사용자 요청 (SIGTERM, exit code 143)

---

## 5. 기술 노트

### 5.1 Python 출력 버퍼링 이슈

백그라운드 실행 시 stdout이 버퍼링되어 실시간 로그가 표시되지 않음.

**현상:**
- 프로세스 활성 (CPU 13-20% 사용)
- 출력 파일 업데이트 안됨

**원인:**
- Python stdout 라인 버퍼링이 아닌 블록 버퍼링 사용
- 프로세스 종료 시에만 버퍼 플러시

**해결 방안 (향후 적용 고려):**
```python
# 방법 1: 환경 변수
PYTHONUNBUFFERED=1 python script.py

# 방법 2: print flush
print("message", flush=True)

# 방법 3: sys.stdout 설정
import sys
sys.stdout.reconfigure(line_buffering=True)
```

### 5.2 파이프라인 중간 저장 불가

현재 파이프라인 구조:
```
Step 1-3: 메모리 처리 → Step 4: DB 저장 (마지막)
```

중간 중단 시 모든 진행 상황 손실됨.

**향후 개선 고려:**
- 단계별 체크포인트 저장
- 재개 가능한 파이프라인 구조

---

## 6. 수정된 파일 목록

| 파일 | 변경 내용 |
|-----|----------|
| `src/llm/prompts.py` | v8 프롬프트 형식, 별점 기반 감정비율 |
| `src/pipeline/batch_pipeline.py` | `_calculate_sentiment_stats()` 헬퍼 함수 |

---

## 7. 향후 작업

1. **파이프라인 재실행**: `리뷰_예약통합.xlsx` 전체 처리 완료
2. **출력 버퍼링 해결**: 실시간 진행 상황 확인 가능하도록 개선
3. **체크포인트 기능**: 중간 저장 및 재개 기능 추가 검토
4. **`llm_provider=None` 버그 수정**: 생성자에서 올바르게 처리되도록 수정

---

## 8. 참고

- 이전 변경 이력: `docs/changelog_20260119.md`
- 프로젝트 문서: `CLAUDE.md`
