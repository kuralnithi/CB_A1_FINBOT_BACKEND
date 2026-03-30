#!/bin/bash
# 1. Run migrations
echo "Running database migrations..."
alembic upgrade head

# 2. Run initial setup (create admin, collections, etc.)
echo "Running initial system setup..."
python do_setup.py

# 3. Start the FastAPI application on dynamic port for Railway/HF
echo "Starting FastAPI on port ${PORT:-8000}..."
uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
