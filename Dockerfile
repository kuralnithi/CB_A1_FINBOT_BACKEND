FROM python:3.11-slim

WORKDIR /app

# Set non-interactive and caching environments
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/model_cache \
    TRANSFORMERS_CACHE=/app/model_cache \
    DATA_DIR=/app/data

# Install system dependencies and uv
# Grouping into a single RUN to reduce layers
RUN apt-get update && apt-get install -y \
    build-essential \
    libpoppler-cpp-dev \
    pkg-config \
    python3-dev \
    curl \
    git \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.local/bin:$PATH"

# 1. Install Python dependencies (Cachable layer)
# COPY requirements.txt first to leverage layer caching
COPY requirements.txt .
RUN uv venv /opt/venv \
    && uv pip install --python /opt/venv/bin/python \
        --no-cache \
        --index-strategy unsafe-best-match \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements.txt \
    && /opt/venv/bin/pip uninstall -y passlib 2>/dev/null || true

ENV PATH="/opt/venv/bin:$PATH"

# Note: Model baking is removed to speed up build time. 
# Models will be downloaded on-demand (Lazy Loading) on the first request.

# Copy application code
COPY . .

# Ensure data directories exist and have permissions
RUN mkdir -p data/general data/finance data/engineering data/marketing data/hr \
    && chmod +x start.sh

# Expose port for Hugging Face Spaces
EXPOSE 7860

# Run the application via startup script
CMD ["./start.sh"]