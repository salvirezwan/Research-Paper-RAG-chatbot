FROM python:3.11-slim

# System deps:
#   libmagic1      — python-magic (file type detection)
#   poppler-utils  — pdftotext fallback used by unstructured
#   libgl1         — OpenCV dep pulled in by some PDF libs
#   nginx          — reverse proxy (single port 7860)
#   supervisor     — process manager (PID 1)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    poppler-utils \
    libgl1 \
    nginx \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# HF Spaces requires UID 1000
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency files first (better layer caching)
COPY pyproject.toml uv.lock ./

# Install dependencies into .venv (no dev extras, frozen lockfile)
RUN uv sync --no-dev --frozen

# Copy application code
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Copy config files
COPY nginx.conf ./nginx.conf
COPY supervisord.conf ./supervisord.conf

# Pre-create runtime dirs under /tmp (writable by non-root)
RUN mkdir -p \
    /tmp/uploads/documents/upload \
    /tmp/uploads/documents/arxiv \
    /tmp/uploads/arxiv \
    /tmp/nginx_client_body \
    /tmp/nginx_proxy \
    /tmp/nginx_fastcgi \
    /tmp/nginx_uwsgi \
    /tmp/nginx_scgi \
    /home/appuser/.cache/huggingface \
    && chown -R appuser:appuser /app /tmp/uploads /home/appuser/.cache \
    /tmp/nginx_client_body /tmp/nginx_proxy /tmp/nginx_fastcgi \
    /tmp/nginx_uwsgi /tmp/nginx_scgi

# Environment
ENV PYTHONUNBUFFERED=1
ENV UPLOAD_DIR=/tmp/uploads/documents
ENV HF_HOME=/home/appuser/.cache/huggingface

# HF Spaces exposes a single port
EXPOSE 7860

USER appuser

CMD ["supervisord", "-c", "/app/supervisord.conf"]
