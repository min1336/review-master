FROM python:3.12-slim-bookworm

# uv binaries only (pinned)
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

WORKDIR /app

# Improve cache behavior in Docker builds
ENV UV_NO_DEV=1 \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install Korean fonts + weasyprint system dependencies for PDF generation
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        fonts-nanum \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libpangoft2-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libcairo2 \
        libharfbuzz0b \
        libfontconfig1 && \
    rm -rf /var/lib/apt/lists/*

# Install dependencies first (better layer caching)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --extra pdf

# Copy application code
COPY . ./

RUN mkdir -p /app/credentials

# Ensure environment is synced against lock (and validates it)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --extra pdf

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "300", "--limit-concurrency", "8"]
