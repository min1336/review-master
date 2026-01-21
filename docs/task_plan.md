# Task Plan

현재 진행 중인 작업 계획. AI가 결정 전 이 파일을 검토하여 목표에 집중합니다.

---

## Current Sprint

### Active Tasks (2026-01-19)
<!-- 현재 진행 중인 작업들 -->

#### 파이프라인 v4.0 완료 ✅
**데이터 소스**: `data/리뷰리스트_매핑완료_20260109.xlsx`

| 항목 | 값 |
|------|-----|
| 총 리뷰 | 88,624개 |
| 파이프라인 | 5단계 (필터링 제거) |

**완료된 작업**:
- [x] 파이프라인 입력 파일 경로 업데이트
- [x] 필터링 단계 제거 (9단계 → 5단계)
- [x] 대시보드 UI 수정 (평점 제거, 정렬 추가)
- [x] 문서 동기화 (5개 파일)

### Completed Tasks
<!-- 완료된 작업들 -->

#### 리뷰 데이터 가공 및 API 매핑 (2026-01-16)
- [x] 원본 Excel 정제 (217,660 → 180,701행)
- [x] 빈 리뷰/욕설/블라인드/삭제 제거
- [x] 컬럼 축소 (18열 → 6열)
- [x] Carmore API로 업체명/주소/위치타입 매핑
- [x] 매핑된 리뷰만 추출 → `리뷰리스트_매핑완료_20260109.xlsx`

#### 시스템 단순화 및 개선 (2026-01-17)
- [x] 1. 가중치 기능 제거 (use_weights=False)
- [x] 2. LLM 프롬프트 출력 예시 개선
- [x] 3. 최근 리뷰 샘플 30개로 변경 (cleanup_reviews)
- [x] 4. API 엔드포인트 외부 접근 설명 (findings.md)
- [x] 5. 스케줄러 개선 설계 (findings.md)
- [x] 6. 환경 변수에서 Gemini 제거

- [x] 태그 시스템 단순화 - 3티어 → 2티어 (2026-01-17)
- [x] Planning with Files 패턴 도입 (2026-01-16)
- [x] Skills 베스트 프랙티스 적용 (2026-01-16)

---

## Backlog

### High Priority
<!-- 우선순위 높은 작업 -->

### Medium Priority
<!-- 중간 우선순위 작업 -->

### Low Priority
<!-- 낮은 우선순위 작업 -->

---

## Goals

### Primary Goal
Review Summary AI 시스템의 안정적 운영 및 개선

### Sub-goals
1. 파이프라인 최적화
2. 코드 품질 향상
3. 문서화 완성도 향상

---

## Skills 사용 템플릿

### Sentiment Analysis Task
```
- [ ] 1. check_thresholds.py 실행
- [ ] 2. test_sentiment.py로 샘플 테스트
- [ ] 3. findings.md에 결과 기록
```

### Keyword Extraction Task
```
- [ ] 1. check_mecab.py로 MeCab 확인
- [ ] 2. test_extraction.py로 추출 테스트
- [ ] 3. findings.md에 결과 기록
```

### Pipeline Execution Task
```
- [ ] 1. check_pipeline_status.py 실행
- [ ] 2. test_provider.py로 LLM 확인
- [ ] 3. BatchPipeline 실행
- [ ] 4. output/ 파일 확인
- [ ] 5. progress.md에 기록
```

### Database Operation Task
```
- [ ] 1. db_health_check.py 실행
- [ ] 2. 쿼리/업로드 수행
- [ ] 3. findings.md에 DB 상태 기록
```

---

## Notes
- 복잡한 작업 시작 전 이 파일에 체크리스트 추가
- 완료 시 체크 표시하고 Completed Tasks로 이동
- 목표에서 벗어나지 않도록 주기적으로 검토
