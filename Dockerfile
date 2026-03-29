FROM python:3.11-slim

WORKDIR /app

# Set non-interactive and caching environments
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/model_cache \
    TRANSFORMERS_CACHE=/app/model_cache \
    DATA_DIR=/app/data

# Install system dependencies and uv
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
COPY requirements.txt .
RUN uv venv /opt/venv \
    && uv pip install --python /opt/venv/bin/python --no-cache -r requirements.txt \
    && /opt/venv/bin/pip uninstall -y passlib 2>/dev/null || true

ENV PATH="/opt/venv/bin:$PATH"

# 2. Bake-in Transformer models (Cachable layer)
# Downloads BGE-small (RAG) and MiniLM (Evaluation) during build
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('BAAI/bge-small-en-v1.5'); \
    SentenceTransformer('all-MiniLM-L6-v2')"

# Copy application code
COPY . .

# Ensure data directories exist and have permissions
RUN mkdir -p data/general data/finance data/engineering data/marketing data/hr \
    && chmod +x start.sh

# Expose port for Hugging Face Spaces
EXPOSE 7860

# Run the application via startup script
CMD ["./start.sh"]