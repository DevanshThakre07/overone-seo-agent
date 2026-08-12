# FP-2 Host — production image for seo-api
# Includes PDF + Postgres driver + Playwright Chromium (SPA sites like Actoro).
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    SEO_STORAGE_PATH=/data/audits.db \
    SEO_PLAYWRIGHT_ENABLED=true \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# System libs for Playwright Chromium + common crawl TLS
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app
COPY config ./config
COPY data/.gitkeep ./data/.gitkeep

RUN pip install --upgrade pip \
    && pip install -e ".[pdf,postgres,playwright]" \
    && playwright install --with-deps chromium

# Persist audits / tokens via volume mount at /data
RUN mkdir -p /data /ms-playwright \
    && chmod 755 /data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/health" || exit 1

CMD ["seo-api"]
