FROM python:3.11-slim

WORKDIR /app

# Install system dependencies and uv
RUN apt-get update && apt-get install -y \
    build-essential \
    libpoppler-cpp-dev \
    pkg-config \
    python3-dev \
    curl \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.local/bin:$PATH"

# Install Python dependencies using uv via a virtual environment
COPY requirements.txt .
RUN uv venv /opt/venv \
    && uv pip install --python /opt/venv/bin/python --no-cache -r requirements.txt \
    && /opt/venv/bin/pip uninstall -y passlib 2>/dev/null || true

# Make sure all subsequent commands use the virtual environment
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY . .

# Ensure startup script is executable
RUN chmod +x start.sh

# Expose port for Hugging Face Spaces
EXPOSE 7860

# Run the application via startup script
CMD ["./start.sh"]