# app/repository/ — DB 접근 레이어

## Conventions

- SQLAlchemy AsyncSession 기반
- 트랜잭션 context manager 사용 필수
- `database.py`: 엔진/세션 팩토리, `get_session()`, `with_retry`
- `orm_models.py`: SQLAlchemy ORM 모델 정의

## Architecture Decisions

- 데이터 정합성: DB 레벨 솔루션(트리거, 제약조건, 계산 컬럼) 우선
- 명시적 요청 없이 API 측 데이터 수정 금지

### branch_tags 테이블

- `created_at` 컬럼 없음 (count, positive/negative/neutral_count, updated_at만 존재)
- 재집계: `DELETE WHERE period_type='all'` + `INSERT ... ON CONFLICT DO UPDATE`

## SQL 마이그레이션

- 유효한 SQL만 출력할 것
- 마크다운 주석, 'Step N' 어노테이션, 비-SQL 텍스트 포함 금지
- `alembic upgrade head` — 적용
- `alembic revision --autogenerate -m "설명"` — 생성

## DB 접속

```bash
PGPASSWORD=devpass psql -h localhost -p 3306 -U n8n_user -d review_summary_db
```

## Schema Reference

> 27개 테이블 컬럼, 관계도, 데이터 흐름 → `.claude/docs/database-schema.md` 참조
> 테이블 요약, 건수, RPC 함수 → `.claude/docs/reference.md` 참조
