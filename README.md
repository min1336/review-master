# Review Summary AI

Carmore 렌트카 리뷰 자동 분석 + 운영팀 대시보드.

## 필요한 것

- Python 3.12+
- PostgreSQL
- [uv](https://docs.astral.sh/uv/) (없으면: `curl -LsSf https://astral.sh/uv/install.sh | sh`)

## 셋업

```bash
# 1. 클론
git clone https://github.com/teamo2dev/Review_Summary_AI.git
cd Review_Summary_AI

# 2. 의존성 설치
uv sync --extra dev

# 3. 환경변수 설정
cp .env.template .env
```

`.env` 파일을 열고 아래 값을 채운다. DB 접속 정보와 OpenAI 키는 팀원에게 공유받는다.

```bash
# 방법 A: URL 한 줄로
DATABASE_URL=postgresql+asyncpg://n8n_user:devpass@localhost:3306/review_summary_db

# 방법 B: 개별 필드로
DATABASE_USER=n8n_user
DATABASE_PASSWORD=devpass
DATABASE_HOST=localhost
DATABASE_PORT=3306
DATABASE_NAME=review_summary_db

# OpenAI (필수)
OPENAI_API_KEY=sk-...
```

```bash
# 4. DB 마이그레이션
uv run alembic upgrade head

# 5. 개발 서버
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

http://localhost:8000 에서 대시보드 확인.

> AWS 키(`AWS_ACCESS_KEY_ID` 등)가 없어도 대시보드, 요약, 리포트는 동작한다. Athena 리뷰 동기화만 안 됨.

## 환경변수

### 필수

| 변수 | 설명 |
|------|------|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:port/dbname` |
| `OPENAI_API_KEY` | OpenAI API 키 |

### 선택

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `API_PREFIX` | `/api` | API 경로 (프로덕션: `/review/api`) |
| `OPENAI_MODEL` | `gpt-4o-mini` | 모델명 |
| `DEBUG` | `false` | 디버그 모드 |
| `N8N_API_KEY` | - | n8n 웹훅 인증 |
| `AWS_ACCESS_KEY_ID` | - | Athena 리뷰 수집용 |
| `AWS_SECRET_ACCESS_KEY` | - | Athena 리뷰 수집용 |

## 자주 쓰는 명령어

```bash
# 개발 서버
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 테스트
uv run pytest

# DB 마이그레이션 (ORM 모델 변경 후)
uv run alembic revision --autogenerate -m "설명"
uv run alembic upgrade head
```

### Docker (프로덕션 환경 로컬 재현)

```bash
cp .env.template .env.prod
# .env.prod에서 API_PREFIX=/review/api, DEBUG=False 로 변경

docker build -t review-api:local .
API_IMAGE=review-api:local docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
docker logs -f review-api          # 로그
docker compose -f docker-compose.prod.yml down   # 중지
```

## 페이지

| URL | 설명 |
|-----|------|
| `/` | 대시보드 |
| `/analysis` | 리뷰 분석 |
| `/pipeline-console` | 파이프라인 콘솔 |
| `/docs` | Swagger API 문서 |
| `/redoc` | ReDoc API 문서 |

## 상세 문서

[`docs.md`](docs.md) -- 아키텍처, 워크플로우, 분석 엔진, 파트너 API, 트러블슈팅

## 배포

`main` 브랜치에 push하면 GitHub Actions가 자동 배포한다.

```
Push to main → Docker 빌드 → AWS 서버 배포 (docker compose up -d)
```

## License

Private - Carmore Internal Use Only
