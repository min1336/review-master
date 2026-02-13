# Gap Analysis Report: pdf (Iteration 3)

> **Feature**: pdf (PDF 생성 인프라 + API 엔드포인트 리팩토링)
> **Date**: 2026-02-13
> **Match Rate**: 89/100
> **Phase**: Check (Iteration 3 — API 리팩토링 후 재분석)
> **Analysis Mode**: Team (3 agents parallel)

---

## Summary

| Category | Score | Weight | Weighted |
|----------|-------|--------|----------|
| Architecture Compliance | 95 | 25% | 23.75 |
| Code Quality | 89 | 25% | 22.25 |
| Performance & Scalability | 93 | 20% | 18.60 |
| Security | 90 | 10% | 9.00 |
| Maintainability | 72 | 15% | 10.80 |
| CLAUDE.md Compliance | 97 | 5% | 4.85 |
| **Total** | | | **89.25 → 89** |

**Progress**: 58 (Initial) → 82 (Iter 1) → 91 (Iter 2) → **89** (Iter 3, 리팩토링 후) → -2 points

> **Note**: Match Rate 감소(-2)는 품질 저하가 아닌, 더 정밀한 분석으로 기존 이슈를 새로 식별한 결과입니다.

---

## Iteration 3 변경 사항 (API 엔드포인트 리팩토링)

### 적용된 개선
1. `start_date: str` → `start_date: date` (FastAPI native 타입) — 8개 엔드포인트
2. `parse_date()` 제거 → `date_to_utc()` 헬퍼 적용
3. `ReportRequest` 인라인 스키마 → `schemas/report.py` 분리
4. `get_review_count_summary()`, `get_top_vehicles()` → Service 레이어로 이동
5. 모든 엔드포인트 `api_` prefix 적용
6. 모든 응답 `api_response()` envelope 통일
7. DI 패턴 `Depends()` 일관 적용

---

## HIGH Issues (1건)

### SEC-1: 500 에러에서 `detail=str(e)` — 민감 정보 노출 위험
- **Files**: report.py (10개소), public_report.py:85
- **Risk**: 프로덕션에서 DB 연결 문자열, 내부 경로 등 노출 가능
- **Fix**: 프로덕션에서는 일반 에러 메시지, 상세 정보는 logger에만 기록
- **Impact**: Security -10

---

## MEDIUM Issues (4건)

### ARCH-3: Service에서 `repository.session.get_client` 직접 import
- **File**: report_service.py:1029, 1333
- **Problem**: Repository 패턴 우회. DI로 주입받은 client 사용이 아닌 직접 세션 획득
- **Impact**: Architecture -1, Maintainability (테스트 용이성 저하)

### ARCH-4: 9개 도메인 모델이 Service 파일에 인라인 정의
- **File**: report_service.py:20-109
- **Models**: ReportData, EvaluationAxis, TagRankItem, VehicleRankItem, AffiliateEvaluation, VehicleEvaluation, VehicleAnalysis, StrengthItem, TopTagItem
- **Fix**: `schemas/report.py` 또는 `models/report.py`로 분리
- **Impact**: Architecture -2

### Q-1: `ReportService.__init__` 파라미터 타입 힌트 누락
- **File**: report_service.py:130
- **Impact**: Code Quality -2, CLAUDE.md Compliance -1

### PERF-1: 전체 행 메모리 로드 후 Python 그룹화
- **File**: report_service.py:1170-1190
- **Problem**: `_get_vehicle_analysis_from_reviews`에서 all_rows.extend() 후 Python에서 그룹화
- **Impact**: Performance -5 (대량 데이터 시 메모리 부담)

---

## LOW Issues (8건)

| ID | 설명 | 파일 | Impact |
|----|------|------|--------|
| ARCH-1 | PDF 엔드포인트 period 해석 로직 API 레이어 존재 | report.py:294-310 | Architecture -0 |
| ARCH-2 | `get_top_vehicles()` static method API에서 직접 호출 | public_report.py:61 | Architecture -0 |
| Q-2 | `_generate_affiliate_text`/`_generate_vehicle_text` LLM 호출 중복 | report_service.py:732-810 | Code Quality -1 |
| Q-5 | `_hr`, `_sub` 약어 함수명 | generator.py:211,225 | Code Quality -1 |
| Q-6 | `date_to_utc` 타입 힌트 문자열 `"date"` 비일관적 | timezone.py:63 | Code Quality -0 |
| Q-8 | `from app.schemas.common` 비일관적 import prefix | report.py:297 | CLAUDE.md -1 |
| M-1 | generator.py 411줄 (권장 300줄 초과, 이전 835줄→대폭 개선) | generator.py | Maintainability -2 |
| M-2 | 업체/차량 평가 PDF 렌더링 중복 (Deferred 유지) | generator.py:123-181 | Maintainability -2 |

---

## Category Detail

### Architecture Compliance: 95/100 (이전 96 → -1)

| 항목 | 점수 | 상세 |
|------|------|------|
| 계층 흐름 | 28/30 | API→Service→Infrastructure 완벽 준수. period 해석 로직 API 잔존 (-2) |
| 의존성 주입 | 25/25 | PDFGenerator DI 주입 개선. Depends() 일관 적용 |
| 날짜 처리 | 20/20 | date 타입 + date_to_utc() + validate_date_range_d() 완벽 |
| 순환 참조 방지 | 14/15 | TYPE_CHECKING 가드 사용. get_client 직접 호출 (-1) |
| DTO/스키마 분리 | 8/10 | ReportRequest 분리 완료. 9개 도메인 모델 인라인 잔존 (-2) |

### Code Quality: 89/100 (이전 88 → +1)

| 항목 | 점수 | 상세 |
|------|------|------|
| 타입 힌트 | 18/20 | __init__ 타입 누락, list 제네릭 미지정 |
| 매직 넘버 | 13/15 | 주요 상수화 완료. PDF 레이아웃 일부 잔존 |
| 함수명 | 14/15 | api_ prefix 완벽. _hr/_sub 약어 |
| 에러 처리 | 19/20 | try-except+logger+HTTPException 일관 적용 |
| 코드 중복 | 12/15 | LLM 호출 패턴, PDF 렌더링 중복 잔존 |
| 파일 크기 | 13/15 | generator.py 411줄 (835→대폭 개선) |

### Performance & Scalability: 93/100 (이전 100 → -7)

| 항목 | 점수 | 상세 |
|------|------|------|
| 비동기 처리 | 28/30 | asyncio.to_thread, asyncio.gather 완벽. sync 비일관 |
| 캐싱 | 25/25 | 클래스 레벨 폰트 캐시 정상 유지 |
| 날짜 파싱 | 20/20 | FastAPI native date 자동 파싱 + 422 자동 에러 |
| 데이터 처리 | 20/25 | top_vehicles 슬라이싱 OK. 메모리 로드 이슈 |

### Security: 90/100 (이전 100 → -10)

| 항목 | 점수 | 상세 |
|------|------|------|
| 입력 검증 | 30/30 | date 타입, regex 제약, 범위 검증 완벽 |
| 출력 인코딩 | 25/25 | urllib.parse.quote, RFC 5987 준수 |
| 인증/인가 | 25/25 | hmac.compare_digest, SecretStr 사용 |
| 에러 노출 | 10/20 | detail=str(e) 민감 정보 노출 위험 (HIGH) |

### Maintainability: 72/100 (이전 67 → +5)

| 항목 | 점수 | 상세 |
|------|------|------|
| 파일 크기 | 12/20 | report_service.py 1622줄. generator.py 411줄 (개선) |
| 코드 중복 | 14/20 | LLM 호출, PDF 렌더링 중복 잔존 |
| 가독성 | 18/20 | docstring 충실, 섹션 구분 명확 |
| 테스트 용이성 | 14/20 | DI mock 가능. get_client 직접 호출이 방해 |
| 변경 용이성 | 14/20 | 레거시/신규 분기 분리됨 |

### CLAUDE.md Compliance: 97/100 (이전 100 → -3)

| 항목 | 점수 | 상세 |
|------|------|------|
| 아키텍처 패턴 | 29/30 | get_client 직접 호출 (Repository 우회) |
| 코딩 규칙 | 29/30 | __init__ 타입 힌트 누락 |
| API 규칙 | 25/25 | Envelope 완벽, 라우트 순서 정상 |
| Git/보안 규칙 | 14/15 | import prefix 비일관 (app. vs 상대경로) |

---

## Endpoint Consistency Matrix

| File | api_response | api_ prefix | Depends() | try-except | Pass |
|------|-------------|-------------|-----------|------------|------|
| report.py (11) | ✅ | ✅ | ✅ | ✅ | ✅ |
| public_report.py (1) | ✅ | ✅ | ✅ | ✅ | ✅ |
| sync.py (6) | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| realtime.py (1) | ✅ | ✅ | ✅ | ✅ | ✅ |
| monthly_scheduler.py (5) | ✅ | ✅ | ✅ | ✅ | ✅ |
| analysis.py (3) | ✅ | ✅ | ✅ | ✅ | ✅ |
| public_summary.py (1) | ✅ | ✅ | ✅ | ✅ | ✅ |
| summaries.py (5) | ✅ | ✅ | ✅ | ✅ | ✅ |
| sentiment.py (2) | ✅ | ✅ | ✅ | ✅ | ✅ |
| tags.py (8) | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## Recommendation

**Match Rate 89%** < 90% → `/pdca iterate pdf` 권장

### Priority 1: SEC-1 해결 (에러 메시지 보안)
- `detail=str(e)` → 프로덕션 일반 메시지 + 로그 상세
- 예상 향상: Security 90→100 → weighted +1.0

### Priority 2: ARCH-4 해결 (도메인 모델 분리)
- 9개 Pydantic 모델 → `schemas/report_models.py` 분리
- 예상 향상: Architecture +2, Maintainability +2 → weighted +0.8

### Priority 3: Q-1 해결 (__init__ 타입 힌트)
- ReportService.__init__ 파라미터 타입 추가
- 예상 향상: Code Quality +2, CLAUDE.md +1 → weighted +0.55

### 예상 최종: 89 + 1.0 + 0.8 + 0.55 = **91.35 → 91** (목표 90% 초과)

---

## Progress History

| Iteration | Match Rate | Delta | Key Changes |
|-----------|-----------|-------|-------------|
| Initial | 58 | - | 최초 분석 |
| Iter 1 | 82 | +24 | API→Service 위임, asyncio.to_thread, 폰트 캐시 |
| Iter 2 | 91 | +9 | 매직넘버 상수화, 미사용 캐시 정리, 타입 힌트 |
| **Iter 3** | **89** | **-2** | API 리팩토링 후 정밀 재분석 (기존 이슈 신규 식별) |

---

## Team Analysis Summary

| Agent | Role | Score(s) |
|-------|------|----------|
| arch-analyzer | Architecture & Layer Compliance | 95/100 |
| quality-analyzer | Code Quality + CLAUDE.md + Maintainability | 89, 97, 72 |
| perf-security-analyzer | Performance + Security + Consistency | 93, 90, Pass |
