#!/bin/bash
set -e

# Ensure Python can find the 'app' module from any script
export PYTHONPATH=/app:$PYTHONPATH

# ─── Debug: Verify critical env vars are loaded ──────────────────────────────
echo "══════════════════════════════════════════════"
echo "  Environment Check:"
echo "    DATABASE_URL: ${DATABASE_URL:+SET (length=${#DATABASE_URL})}${DATABASE_URL:- ❌ NOT SET}"
echo "    QDRANT_HOST:  ${QDRANT_HOST:+SET}${QDRANT_HOST:- ❌ NOT SET}"
echo "    GROQ_API_KEY: ${GROQ_API_KEY:+SET}${GROQ_API_KEY:- ❌ NOT SET}"
echo "    LLM_PROVIDER: ${LLM_PROVIDER:-not set (will default to groq)}"
echo "══════════════════════════════════════════════"

# ─── 1. Database Migrations ──────────────────────────────────────────────────
echo "══════════════════════════════════════════════"
echo "  [1/3] Running database migrations..."
echo "══════════════════════════════════════════════"
if [ -z "$DATABASE_URL" ]; then
    echo "  ⚠️  DATABASE_URL not set — skipping migrations."
else
    if timeout 60 alembic upgrade head; then
        echo "  ✅ Migrations completed successfully."
    else
        echo "  ⚠️  WARNING: Migrations failed or timed out. Continuing anyway..."
    fi
fi

# ─── 2. Initial Setup (admin user, Qdrant collections) ───────────────────────
echo "══════════════════════════════════════════════"
echo "  [2/3] Running initial system setup..."
echo "══════════════════════════════════════════════"
if timeout 60 python scripts/setup.py; then
    echo "  ✅ System setup completed successfully."
else
    echo "  ⚠️  WARNING: Setup script failed or timed out. Continuing anyway..."
fi

# ─── 3. Start the Application ────────────────────────────────────────────────
# Railway/Render inject $PORT. Default to 10000 if not set.
PORT="${PORT:-10000}"

echo "══════════════════════════════════════════════"
echo "  [3/3] Starting FinBot API on port ${PORT}..."
echo "══════════════════════════════════════════════"

exec gunicorn main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind "0.0.0.0:${PORT}" \
    --workers 1 \
    --timeout 180 \
    --graceful-timeout 30 \
    --access-logfile - \
    --error-logfile -
