# Dockerfile
#
# SAGE application image.
# Used by: web (Django dev server), celery_worker (Week 2), flower (Week 2).
#
# Development image — not production-hardened.
# Production additions required before go-live:
#   - Non-root user (addgroup/adduser)
#   - Multi-stage build to strip dev dependencies
#   - gunicorn instead of runserver
#   - COPY-only deploy (no volume mount)

FROM python:3.12-slim

# ── Build arguments ──────────────────────────────────────────────────────────
# Allows overriding the Python environment at build time if needed.
ARG PYTHON_VERSION=3.12

# ── Environment variables ────────────────────────────────────────────────────
ENV PYTHONDONTWRITEBYTECODE=1 \
    # Prevents .pyc files from being written to disk
    PYTHONUNBUFFERED=1 \
    # Forces stdout/stderr to flush immediately (essential for Docker logs)
    PIP_NO_CACHE_DIR=1 \
    # Keeps the image smaller by not caching pip downloads
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TIKTOKEN_CACHE_DIR=/app/.tiktoken_cache \
    # Pinned cache directory so the pre-downloaded tokenizer survives COPY
    HF_HOME=/app/.hf_cache

# ── System dependencies ──────────────────────────────────────────────────────
# libglib2.0-0  — required by opencv-python-headless (GLib runtime)
# libgomp1      — required by opencv-python-headless (OpenMP parallel processing)
# libsm6        — required by some OpenCV drawing operations (X Session Management)
# libxext6      — required by some OpenCV operations (X Extensions)
#
# psycopg2-binary, PyMuPDF, and tiktoken ship their own compiled binaries
# and do not require additional system packages.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgomp1 \
        libsm6 \
        libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python dependencies ──────────────────────────────────────────────────────
# Copied before application code to maximise layer caching.
# This layer is only rebuilt when requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── tiktoken tokenizer pre-cache ─────────────────────────────────────────────
# tiktoken downloads the cl100k_base BPE tokenizer data from the internet
# on first import. Pre-downloading during the image build:
#   1. Eliminates the runtime network dependency
#   2. Makes container startup deterministic
#   3. Speeds up the first request after container start
#
# Requires internet access at build time.
# The downloaded files are stored at TIKTOKEN_CACHE_DIR (/app/.tiktoken_cache).
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"
# RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

# ── Application code ─────────────────────────────────────────────────────────
# In development, this layer is overridden by the bind mount:
#   volumes:
#     - .:/app
# Changes to source files on the host are reflected immediately in the container.
# This COPY is retained to make the image self-contained for CI and production.
COPY . .

# ── Runtime directories ───────────────────────────────────────────────────────
# Created here so they exist in the image layer before any volume mounts.
# The bind mount in docker-compose overlays /app but these subdirectories
# are created on the host by the setup command (see README).
RUN mkdir -p \
    /app/media/documents \
    /app/media/images \
    /app/.tiktoken_cache

EXPOSE 8000