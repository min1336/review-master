# Review Summary AI

Carmore 렌트카 리뷰 자동 분석 + 운영팀 대시보드.

## 필요한 것

- Python 3.12+
- PostgreSQL 16+ (asyncpg 드라이버 사용 — MySQL, SQLite 불가)
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

`.env` 파일을 열고 DB 접속 정보와 OpenAI 키를 채운다. 두 가지 방식 중 하나를 선택:

```bash
# 방법 A: URL 한 줄로 (우선 적용됨)
DATABASE_URL=postgresql+asyncpg://<user>:<password>@<host>:<port>/<dbname>

# 방법 B: 개별 필드로
DATABASE_USER=<user>
DATABASE_PASSWORD=<password>
DATABASE_HOST=<host>
DATABASE_PORT=<port>
DATABASE_NAME=<dbname>

# OpenAI (필수)
OPENAI_API_KEY=<your-openai-api-key>
```

### 4. DB 준비

기존 DB에 접속하는 경우 이 단계를 건너뛰고 `.env`만 채우면 된다.

**새 DB를 만들어야 하는 경우:**

```bash
# PostgreSQL 접속 (본인 환경에 맞게 포트 지정)
sudo -u postgres psql -p <port>

# 사용자 + DB 생성
CREATE USER <user> WITH PASSWORD '<password>';
CREATE DATABASE <dbname> OWNER <user>;
GRANT ALL PRIVILEGES ON DATABASE <dbname> TO <user>;
\q
```

### Dev DB 생성 (prod 복사)

prod DB를 템플릿으로 dev DB를 만든다. DataGrip 등에서 `postgres` DB에 연결 후 실행:

```sql
-- 1. review_summary_db 활성 연결 종료
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'review_summary_db' AND pid <> pg_backend_pid();

-- 2. prod를 템플릿으로 dev DB 생성 (스키마 + 데이터 + 인덱스 전부 복사)
CREATE DATABASE review_summary_db_dev TEMPLATE review_summary_db;
```

앱에서 dev DB를 사용하려면 `.env`에서 DB 이름만 변경:

```bash
DATABASE_NAME=review_summary_db_dev
```

> `TEMPLATE`은 원본 DB에 활성 연결이 있으면 실패한다. `pg_terminate_backend`로 먼저 끊어야 한다.

### 5. DB 초기화

```bash
uv run alembic upgrade head
```

신규 DB든 기존 DB든 동일하게 위 명령어 하나로 처리된다. 테이블, stored function, trigger가 모두 포함되어 있다.

```bash
# 6. 개발 서버
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

http://localhost:8000 에서 대시보드 확인.
https://n8n-cloud.carmore.kr/review/analysis # 실 사이트


ssh carmore-n8n-cloud # EC2 접속

> AWS 키(`AWS_ACCESS_KEY_ID` 등)가 없어도 대시보드, 요약, 리포트는 동작한다. Athena 리뷰 동기화만 안 됨.

## 환경변수

### 필수

| 변수 | 설명 |
|------|------|
| `DATABASE_URL` | PostgreSQL 연결 URL (`postgresql+asyncpg://...`) |
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
