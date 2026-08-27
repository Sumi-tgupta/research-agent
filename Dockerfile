# syntax=docker/dockerfile:1
#
# Backend API image for the Apex-Research FastAPI service (Phase 13).
#
# This builds the Python service ONLY. The Next.js frontend in web/ deploys
# separately to Vercel (see web/vercel.json + DEPLOY.md), so it is excluded from
# this image via .dockerignore — keeping the build context small and the image
# focused on the API.
#
# Designed for the free hosting tier (Hugging Face Spaces / Render / Fly.io):
# the server binds to $PORT, which those platforms inject. Locally it defaults
# to 8000. HF Spaces expects 7860 — set PORT=7860 there (documented in DEPLOY.md).

FROM python:3.13-slim AS base

# - PYTHONUNBUFFERED: stream logs straight to the platform's capture (no buffering).
# - PYTHONDONTWRITEBYTECODE: don't litter the image with .pyc files.
# - PIP_NO_CACHE_DIR / version-check: smaller image, quieter build.
# - HF_HOME / SENTENCE_TRANSFORMERS_HOME: pin the embedding-model cache to a
#   writable path owned by the non-root user (the model downloads on first use).
# - PORT: default; overridden by the platform at runtime.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/home/app/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/home/app/.cache/huggingface \
    PORT=8000

# Runtime + build libs:
#   - libgomp1      : OpenMP runtime required by faiss-cpu / torch at import time.
#   - build-essential: fallback compiler for any dependency without a cp313 wheel.
#   - curl          : used only by the container HEALTHCHECK below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies in their own layer BEFORE copying the app code, so that
# editing source doesn't invalidate the (slow) pip install layer on rebuilds.
COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# App source. .dockerignore trims this to what the API needs (no .venv, no
# web/ or frontend/, no local caches/db, no tests).
COPY . .

# Drop root: create an unprivileged user and hand it the app + model cache dirs.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /home/app/.cache/huggingface \
    && chown -R app:app /app /home/app
USER app

# Documentation only (EXPOSE can't read the runtime $PORT). The real bind is in
# CMD via ${PORT}. On HF Spaces, set PORT=7860.
EXPOSE 8000

# Fail the container's health if the API stops answering. start-period gives the
# app time to import the heavy ML deps and warm up on a cold free-tier instance.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT}/health" || exit 1

# `exec` so uvicorn becomes PID 1 and receives SIGTERM directly (clean shutdown);
# sh -c is needed to expand ${PORT} at runtime. One worker on purpose: the free
# tier is memory-constrained and the ML deps are heavy — scale via the platform's
# instances, not in-container workers.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
