#!/bin/bash
# 1. Run migrations
echo "Running database migrations..."
alembic upgrade head

# 2. Run initial setup (create admin, collections, etc.)
echo "Running initial system setup..."
python do_setup.py

# 3. Start the FastAPI application
echo "Starting FastAPI on port 7860..."
uvicorn main:app --host 0.0.0.0 --port 7860
