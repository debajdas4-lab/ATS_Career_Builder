# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# Single image that can run EITHER the API or the UI, selected at runtime via
# the SERVICE env var (api|ui). This keeps the build cache shared and the
# deployment simple for an internal team tool.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    SERVICE=api

WORKDIR /app

# System deps kept minimal (slim). curl is used for the healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for better layer caching.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# App source
COPY . .

# Run as a non-root user (enterprise hardening).
RUN useradd -m -u 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000 8501

# Healthcheck targets the API root (UI containers override HEALTHCHECK via compose).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT}/" || exit 1

COPY --chown=appuser:appuser docker-entrypoint.sh /app/docker-entrypoint.sh
ENTRYPOINT ["/app/docker-entrypoint.sh"]
