# Gap Analysis Report: pdf

> **Feature**: pdf (PDF 생성 인프라)
> **Date**: 2026-02-13 (Final)
> **Match Rate**: 91/100
> **Phase**: Act (Iteration 2 완료 - 90% 임계값 달성)

---

## Summary

| Category | Score | Weight | Weighted |
|----------|-------|--------|----------|
| Architecture Compliance | 96 | 25% | 24.00 |
| Code Quality | 88 | 25% | 22.00 |
| Performance & Scalability | 100 | 20% | 20.00 |
| Security | 100 | 10% | 10.00 |
| Maintainability | 67 | 15% | 10.00 |
| CLAUDE.md Compliance | 100 | 5% | 5.00 |
| **Total** | | | **91.00** |

**Progress**: 58 (Initial) → 82 (Iter 1) → **91** (Iter 2) → +33 points total

---

## ✅ RESOLVED (Iteration 1) — HIGH Issues

### H-1: API → Infrastructure 직접 호출 (아키텍처 위반)
- **Fix**: `report_service.py` - `generate_pdf()` 메서드 추가
- **Validation**: `report.py` - `service.generate_pdf(report)` 호출

### H-2: 동기 PDF 생성 → 이벤트 루프 블로킹
- **Fix**: `report_service.py` - `asyncio.to_thread()` 래핑
- **Impact**: Performance 45 → 100

### H-3: 폰트 탐색 매 인스턴스마다 실행
- **Fix**: `generator.py` - 클래스 레벨 `_font_cache` + `@classmethod _discover_fonts()`
- **Impact**: Performance 45 → 100

---

## ✅ RESOLVED (Iteration 2) — MEDIUM Issues

### M-3: 매직넘버 상수화
- **Fix**: `AXIS_NAME_W=27`, `BAR_WIDTH_RATIO=0.55`, `EST_CHARS_PER_LINE=45` 클래스 상수 정의
- **Impact**: Code Quality 65 → 88

### M-4: 미사용 캐시 export 정리
- **Fix**: `__init__.py`에서 `NullCache`, `PDFCacheStrategy` export 제거
- `cache.py`는 확장용 인터페이스로 유지
- **Impact**: Architecture Compliance +1

### 타입 힌트 개선
- `_ratio_color()` 반환 타입: `tuple` → `tuple[int, int, int]`
- **Impact**: CLAUDE.md Compliance 75 → 100

---

## Deferred Issues (기술 부채)

### M-1: 파일 크기 835줄 (권장 300줄 초과)
- **Status**: Deferred (의도적)
- **Reason**: 논리적 섹션이 `===` 구분자로 명확히 분리됨. 파일 분할 시 응집도 저하 위험.
- **Plan**: 팀 규모 5명 이상 시 분리 검토

### M-2: 새/레거시 포맷 간 중복 로직 70-85%
- **Status**: Deferred (의도적)
- **Reason**: 두 포맷이 독립적으로 진화하기 위한 설계 결정
- **Plan**: 포맷 수렴 시 Template Method 패턴 적용

---

## Architecture Verification ✅

```
API (report.py)
  ↓ service.generate_pdf()
Service (report_service.py)
  ↓ asyncio.to_thread(pdf_generator.generate_simple)
Infrastructure (generator.py)
```

---

## Recommendation

**Match Rate 91%** >= 90% → `/pdca report pdf` 권장
