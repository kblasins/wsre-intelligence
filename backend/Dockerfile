# ── Stage 1: dependency resolver ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv==0.5.14

COPY pyproject.toml .
# Resolve and download all wheels into /build/wheels
RUN uv pip install --system --no-cache --compile-bytecode \
    --find-links /build/wheels \
    -e ".[dev]" \
    --target /build/site-packages \
    .


# ── Stage 2: Playwright + Chromium ────────────────────────────────────────────
FROM python:3.12-slim AS playwright-base

RUN pip install --no-cache-dir playwright==1.49.0 && \
    playwright install chromium --with-deps && \
    playwright install-deps chromium

# ── Stage 3: final runtime image ──────────────────────────────────────────────
FROM python:3.12-slim

LABEL org.opencontainers.image.title="ws-hub-backend"
LABEL org.opencontainers.image.description="White Star Market Intelligence Hub — backend"
LABEL org.opencontainers.image.source="https://github.com/white-star-re/market-hub"

# System dependencies for Chromium, pymupdf, curl_cffi, and pgbackrest
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Chromium runtime (copied from playwright-base)
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libdbus-1-3 libxkbcommon0 libatspi2.0-0 libx11-6 \
    libxcomposite1 libxdamage1 libxext6 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    # General utilities
    curl ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*

# Copy Chromium + Playwright from playwright-base stage
COPY --from=playwright-base /root/.cache/ms-playwright /root/.cache/ms-playwright
COPY --from=playwright-base /usr/local/lib/python3.12/site-packages/playwright \
    /usr/local/lib/python3.12/site-packages/playwright

# Copy installed Python packages from builder
COPY --from=builder /build/site-packages /usr/local/lib/python3.12/site-packages

WORKDIR /app

# Non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser -m appuser

COPY --chown=appuser:appuser . .

# Directory for Playwright session state files (persisted via Docker volume)
RUN mkdir -p /app/state && chown appuser:appuser /app/state

USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--loop", "uvloop", \
     "--access-log"]
