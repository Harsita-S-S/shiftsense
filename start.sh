#!/usr/bin/env bash
# ================================================================
#  ShiftSense v5 — Start Both Servers
#  Usage:  bash start.sh
# ================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ShiftSense v5 — Hybrid Architecture Startup"
echo "═══════════════════════════════════════════════════════"
echo ""

# ── Shared config ─────────────────────────────────────────────────
export DB_PATH="$SCRIPT_DIR/shiftsense.db"
export JWT_SECRET="${JWT_SECRET:-shiftsense-dev-secret-change-in-prod}"
NODE_PORT="${PORT:-3000}"
FASTAPI_PORT=3001

# ── Port conflict check ───────────────────────────────────────────
for PORT_CHECK in $NODE_PORT $FASTAPI_PORT; do
  if lsof -ti tcp:$PORT_CHECK &>/dev/null; then
    echo "❌ Port $PORT_CHECK is already in use. Free it and try again."
    echo "   Run: kill \$(lsof -ti tcp:$PORT_CHECK)"
    exit 1
  fi
done

# ── Check Node.js ─────────────────────────────────────────────────
if ! command -v node &>/dev/null; then
  echo "❌ Node.js not found. Install from https://nodejs.org"
  exit 1
fi

# ── Install Node dependencies if needed ──────────────────────────
if [ ! -d "frontend/node_modules" ]; then
  echo "📦 Installing Node.js dependencies..."
  cd frontend && npm install && cd ..
fi

# ── Start Node.js ─────────────────────────────────────────────────
echo "🟢 Starting Node.js backend on port $NODE_PORT..."
(cd "$SCRIPT_DIR/frontend" && PORT=$NODE_PORT DB_PATH="$DB_PATH" JWT_SECRET="$JWT_SECRET" node server.js) &
NODE_PID=$!
echo "   Node PID: $NODE_PID"
sleep 1

# Verify Node actually started
if ! kill -0 $NODE_PID 2>/dev/null; then
  echo "❌ Node.js failed to start. Check frontend/server.js for errors."
  exit 1
fi

# ── Trap: only kill Node on exit ──────────────────────────────────
cleanup() {
  echo ""
  echo "Shutting down..."
  kill $NODE_PID 2>/dev/null && echo "Stopped Node.js."
  [ -n "$FASTAPI_PID" ] && kill $FASTAPI_PID 2>/dev/null && echo "Stopped FastAPI."
  exit 0
}
trap cleanup INT TERM

# ── Check Python + FastAPI (optional) ────────────────────────────
PYTHON=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then
    PYTHON="$cmd"
    break
  fi
done

FASTAPI_PID=""
if [ -z "$PYTHON" ]; then
  echo "⚠️  Python not found — analytics (v2) unavailable. App runs in basic mode."
elif ! $PYTHON -c "import fastapi" 2>/dev/null; then
  echo "⚠️  FastAPI not installed — analytics (v2) unavailable."
  echo "   To enable: pip install -r requirements.txt"
else
  echo "🐍 Starting FastAPI analytics backend on port $FASTAPI_PORT..."
  (cd "$SCRIPT_DIR" && $PYTHON -m uvicorn backend.app.main:app --port $FASTAPI_PORT --host 0.0.0.0) &
  FASTAPI_PID=$!
  sleep 1
  if ! kill -0 $FASTAPI_PID 2>/dev/null; then
    echo "⚠️  FastAPI failed to start — analytics (v2) unavailable. Node.js still running."
    FASTAPI_PID=""
  else
    echo "   FastAPI PID: $FASTAPI_PID"
  fi
fi

echo ""
echo "   App:    http://localhost:$NODE_PORT"
echo "   API v1: http://localhost:$NODE_PORT/api"
if [ -n "$FASTAPI_PID" ]; then
  echo "   API v2: http://localhost:$FASTAPI_PORT/api/v2"
else
  echo "   API v2: unavailable (analytics use city averages as fallback)"
fi
echo ""
echo "   Press Ctrl+C to stop."
echo "═══════════════════════════════════════════════════════"
echo ""

# Keep alive — wait for Node (primary process)
wait $NODE_PID