.PHONY: run local local-prod stop logs build clean

# 한 번에 빌드, 실행, 로그 확인
run: local-prod
	docker logs -f review-api

# Docker 이미지 빌드
build:
	docker build -t review-api:local .

# 로컬 개발 서버 실행
local:
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Docker 컨테이너 실행 (build 후 실행)
local-prod: build
	docker compose -f docker-compose.prod.yml up

# Docker 컨테이너 중지 및 삭제
local-prod-stop:
	docker compose -f docker-compose.prod.yml down

# Docker 로그 확인
local-prod-logs:
	docker compose -f docker-compose.prod.yml logs -f

# Docker 이미지 및 컨테이너 정리
clean:
	docker compose -f docker-compose.prod.yml down
	docker rmi review-api:local || true