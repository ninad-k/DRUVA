# syntax=docker/dockerfile:1.7
# =============================================================================
# DHRUVA Backend — multi-stage Docker image
# =============================================================================

ARG PYTHON_VERSION=3.12

# --- Builder stage ----------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential curl git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt ./
RUN pip install --upgrade pip wheel \
 && pip wheel --wheel-dir=/wheels -r requirements.txt

# --- Runtime stage ----------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DHRUVA_ENV=production

RUN apt-get update && apt-get install -y --no-install-recommends \
      libpq5 curl tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system dhruva \
    && useradd --system --gid dhruva --home /app dhruva

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt ./
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
 && rm -rf /wheels

COPY --chown=dhruva:dhruva . .

USER dhruva

EXPOSE 8000 50051 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health/live || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
