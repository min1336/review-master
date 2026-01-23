FROM python:3.12-slim-bookworm

# uv binaries only (pinned)
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

WORKDIR /app

# Improve cache behavior in Docker builds
ENV UV_NO_DEV=1 \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install dependencies first (better layer caching)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project

# Copy application code
COPY . ./

RUN mkdir -p /app/credentials

# Ensure environment is synced against lock (and validates it)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
