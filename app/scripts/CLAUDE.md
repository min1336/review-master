# app/scripts/ — 운영 스크립트

## Commands

| Command | Description |
| ------- | ----------- |
| `python -m py_compile <file.py>` | 문법 검사 |
| `alembic upgrade head` | DB 마이그레이션 적용 |
| `alembic revision --autogenerate -m "설명"` | 마이그레이션 생성 |
| `python app/scripts/run_auto_mapping.py` | 키워드 자동 매핑 |
| `cd app && ../.venv/bin/python scripts/retag_reviews.py` | 리뷰 재태깅 (**app/ 에서 실행 필수**) |

## Testing

- 버그 수정 시 대상 + 인접 카테고리 모두 기존 테스트 실행하여 회귀 확인
- 수정 → 전체 테스트 → 통과 확인 순서 필수
