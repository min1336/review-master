.PHONY: run dev up down logs clean

IMAGE   := review-api:local
COMPOSE := API_IMAGE=$(IMAGE) docker compose --env-file .env.local -f docker-compose.local.yml

# 로컬 개발 서버 (hot-reload)
dev:
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Docker 빌드 → 실행 → 로그 (Ctrl+C로 로그만 종료)
run: build up
	docker logs -f review-api

# Docker 이미지 빌드
build:
	docker build -t $(IMAGE) .

# 컨테이너 백그라운드 실행
up: build
	$(COMPOSE) up -d

# 컨테이너 중지
down:
	$(COMPOSE) down

# 로그 확인
logs:
	$(COMPOSE) logs -f

# 이미지 + 컨테이너 정리
clean: down
	docker rmi $(IMAGE) || true
