# Progress Log

각 시도와 실패를 기록하는 파일. 같은 실수 반복 방지.

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
