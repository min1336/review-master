# Progress Log

각 시도와 실패를 기록하는 파일. 같은 실수 반복 방지.

---

## 2026-01-16

### 리뷰 데이터 가공 및 API 매핑
**Status**: Completed

**목표**:
원본 Excel 데이터를 정제하고 Carmore API로 업체 정보 매핑

**What was done**:
1. 원본 데이터 정제 (217,660 → 180,701행)
   - 빈 리뷰 제거: -33,490
   - 욕설 포함 제거: -236
   - 블라인드/삭제 제거: -4,021
2. 컬럼 축소 (18열 → 6열)
3. Carmore API로 업체명/주소/위치타입 매핑
4. 매핑된 리뷰만 추출 (88,624행)

**Issues encountered**:
- JEJU locationType API 서버 에러 (500)
- 개별 지점 조회 API 서버 에러 (500)
- 관리자 API 인증 필요 (401)
- 리뷰 API에 리뷰번호/예약번호 없음 → Excel 매칭 불가
- 예약 API로 완료된 예약 조회 불가

**Solutions tried**:
1. PARTNERS + GLOBAL locationType 조회 → GLOBAL은 PARTNERS와 동일
2. 개별 지점 조회 시도 → 실패
3. 예약번호로 차종 조회 시도 → 실패

**Result**: Partial Success (49% 매핑률)

**Output files**:
- `data/리뷰리스트_매핑완료_20260109.xlsx` (88,624행, 353개 지점)

**Lessons learned**:
- API는 활성 지점만 제공 (비활성/폐업 지점 미포함)
- 차종 정보는 API 기반 신규 수집 시에만 획득 가능
- Excel↔API 매칭 키가 없어 기존 데이터 enrichment 한계

---

## 2026-01-17

### 시스템 단순화 Sprint
**Status**: Completed

**목표**:
1. 가중치 기능 제거
2. 프롬프트 출력 예시 개선
3. 최근 리뷰 샘플 30개로 변경 (1개월 후 자동 삭제)
4. API 엔드포인트 외부 접근 설명
5. 스케줄러 개선 (API 리뷰 수집 → 지점별/시기별 업데이트)
6. 환경 변수에서 Gemini 제거

**완료 상황**:
- [x] 태그 시스템 단순화 완료 (3티어 → 2티어)
- [x] 가중치 기능 제거 (aggregator.py: use_weights=False)
- [x] 프롬프트 예시 개선 (prompts.py: 더 자연스러운 표현)
- [x] 리뷰 샘플 30개 제한 (cleanup_reviews 함수 추가)
- [x] 스케줄러 개선 설계 (findings.md에 문서화)
- [x] Gemini 제거 (settings.py, llm/__init__.py)

**변경된 파일**:
- `src/analysis/keywords/aggregator.py` - use_weights=False 기본값
- `web/supabase_client.py` - count 기반 정렬, cleanup_reviews 함수 추가
- `web/app.py` - cleanup API 업데이트
- `src/llm/prompts.py` - Few-shot 예시 개선
- `src/config/settings.py` - Gemini 설정 제거
- `src/llm/__init__.py` - GeminiProvider 제거, get_provider() 추가
- `docs/findings.md` - API 외부 접근, 스케줄러 설계 문서화

---

### 변경사항 커밋 + 파이프라인 최적화
**Status**: Completed

**What was done**:
- 5개 커밋 생성:
  1. `feat: Add DI container and DTO classes`
  2. `docs: Add planning files pattern`
  3. `chore: Update project documentation`
  4. `refactor: Optimize BatchPipeline performance and clarity`
  5. `feat: Add run_with_result() method for DTO support`

**Pipeline Optimizations**:
1. Step 5 메서드명 명확화 (`_filter_positive` → `_compute_sentiment_stats`)
2. 지점명 조회 캐싱 (O(1) 조회)
3. 부정 패턴 정규표현식 컴파일
4. 검증 실패 시 재시도 로직 (max_retries=2)
5. 타입 힌트 강화 (LLMProvider 타입 별칭)
6. 파일 로드 에러 처리 강화

**New features**:
- `run_with_result()` 메서드: PipelineResultDTO 반환

**Result**: Success

---

## 2026-01-16

### Planning with Files 패턴 도입
**Status**: Completed

**What was done**:
- task_plan.md 생성 (작업 계획 추적)
- findings.md 생성 (연구 결과 저장)
- progress.md 생성 (진행 상황 기록)

**Result**: Success

---

### Skills 베스트 프랙티스 적용
**Status**: Completed

**What was done**:
- 5개 Skills에 Workflow Checklist 추가
- analyzing-sentiment, extracting-keywords에 헬퍼 스크립트 생성
- allowed-tools 문법 정리 (`Bash(python:*)` → `Bash`)
- Requirements 섹션 추가
- Planning Integration 섹션 추가

**New files created**:
```
.claude/skills/analyzing-sentiment/scripts/
├── test_sentiment.py
└── check_thresholds.py

.claude/skills/extracting-keywords/scripts/
├── test_extraction.py
└── check_mecab.py
```

**Issues encountered**:
- pydantic_settings 모듈 누락 → `pip install pydantic-settings`로 해결
- settings 속성 이름 변경 (대문자 → 소문자) → 스크립트 수정
- analyze_with_detail 반환값 형식 (tuple) → 스크립트 수정

**Result**: Success

**Lessons learned**:
- Settings 클래스 사용 시 `get_settings()` 함수로 접근
- analyze_with_detail은 `(SentimentResult, bool)` 튜플 반환
- extract() 메서드는 단일 문자열도 처리 가능

---

## Template

### [작업명]
**Status**: In Progress / Completed / Failed

**What was done**:
- 작업 내용 1
- 작업 내용 2

**Issues encountered**:
- 문제 1
- 문제 2

**Solutions tried**:
1. 시도 1 - 결과
2. 시도 2 - 결과

**Result**: Success / Failed / Partial

**Lessons learned**:
- 교훈 1
- 교훈 2

---

## Failed Attempts Archive

실패한 시도들을 기록. 같은 실수 반복 방지.

### Example: [실패한 작업명]
**Date**: YYYY-MM-DD
**What went wrong**: 설명
**Root cause**: 근본 원인
**Don't do this again**: 피해야 할 것
