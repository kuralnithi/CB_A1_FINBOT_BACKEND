FROM python:3.11-slim

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/model_cache \
    TRANSFORMERS_CACHE=/app/model_cache \
    DATA_DIR=/app/data \
    PATH="/opt/venv/bin:/root/.local/bin:$PATH"

# 1. Install system dependencies
RUN apt-get update && apt-get install -y \
    libpoppler-cpp-dev \
    pkg-config \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 2. Add uv from its official image (cleaner than curl)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Install Python deps
COPY requirements.txt .
RUN uv venv /opt/venv \
    && uv pip install --python /opt/venv/bin/python \
    --no-cache \
    --index-strategy unsafe-best-match \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# Copy code
COPY . .

# Setup dirs
RUN mkdir -p data/general data/finance data/engineering data/marketing data/hr \
    && mkdir -p /app/model_cache \
    && sed -i 's/\r$//' start.sh \
    && chmod +x start.sh

EXPOSE 7860

CMD ["./start.sh"]