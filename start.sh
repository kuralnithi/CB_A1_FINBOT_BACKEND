#!/bin/bash
set -e

# ─── 1. Database Migrations ──────────────────────────────────────────────────
echo "══════════════════════════════════════════════"
echo "  [1/3] Running database migrations..."
echo "══════════════════════════════════════════════"
if timeout 60 alembic upgrade head; then
    echo "  ✅ Migrations completed successfully."
else
    echo "  ⚠️  WARNING: Migrations failed or timed out. Continuing anyway..."
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
# Render injects $PORT. Default to 10000 if not set.
PORT="${PORT:-10000}"

echo "══════════════════════════════════════════════"
echo "  [3/3] Starting FinBot API on port ${PORT}..."
echo "══════════════════════════════════════════════"

# Use 'exec' to replace shell with the server process (PID 1 for signal handling).
# Gunicorn + UvicornWorker = production-grade ASGI server.
# Workers=1 to fit within Render free tier 512MB RAM. Increase to 2-4 on paid plans.
exec gunicorn main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind "0.0.0.0:${PORT}" \
    --workers 1 \
    --timeout 180 \
    --graceful-timeout 30 \
    --access-logfile - \
    --error-logfile -
