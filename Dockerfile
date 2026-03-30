FROM python:3.11-slim

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/model_cache \
    TRANSFORMERS_CACHE=/app/model_cache \
    DATA_DIR=/app/data \
    PATH="/opt/venv/bin:/root/.local/bin:$PATH"

# Install uv first (cached)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Install minimal system deps
RUN apt-get update && apt-get install -y \
    libpoppler-cpp-dev \
    pkg-config \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN uv venv /opt/venv \
    && uv pip install --python /opt/venv/bin/python \
    --no-cache \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# Copy code
COPY . .

# Setup dirs
RUN mkdir -p data/general data/finance data/engineering data/marketing data/hr \
    && mkdir -p /app/model_cache \
    && chmod +x start.sh

EXPOSE 7860

CMD ["./start.sh"]