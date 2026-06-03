FROM python:3.11-slim

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/app/model_cache \
    TRANSFORMERS_CACHE=/app/model_cache \
    DATA_DIR=/app/data \
    PATH="/opt/venv/bin:/root/.local/bin:$PATH"

# 1. Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpoppler-cpp-dev \
    pkg-config \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 2. Add uv from its official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 3. Install Python deps (cached layer — only re-runs if requirements.txt changes)
COPY requirements.txt .
RUN uv venv /opt/venv \
    && uv pip install --python /opt/venv/bin/python \
    --no-cache \
    --index-strategy unsafe-best-match \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# 4. Copy application code
COPY . .

# 5. Setup directories and fix line endings
RUN mkdir -p data/general data/finance data/engineering data/marketing data/hr \
    && mkdir -p /app/model_cache \
    && sed -i 's/\r$//' start.sh \
    && chmod +x start.sh

# Render injects PORT at runtime (default 10000). We EXPOSE for documentation only.
EXPOSE ${PORT:-10000}

# Health check — Render uses HTTP health checks, but this is a Docker-level fallback
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:${PORT:-10000}/health || exit 1

CMD ["./start.sh"]