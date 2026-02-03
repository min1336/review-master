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
	docker stop review-api || true
	docker rm review-api || true
	docker run -d --name review-api -p 8000:8000 --cpus="0.5" --memory="512m" --env-file .env -e PYTHONUNBUFFERED=1 review-api:local

# Docker 컨테이너 중지 및 삭제
local-prod-stop:
	docker stop review-api && docker rm review-api

# Docker 로그 확인
local-prod-logs:
	docker logs -f review-api

# Docker 이미지 및 컨테이너 정리
clean:
	docker stop review-api || true
	docker rm review-api || true
	docker rmi review-api:local || true