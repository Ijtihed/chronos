#!/usr/bin/env bash
# Restart the CHRONOS uvicorn server cleanly.
#
# Use after editing .env (e.g. renewing GEMINI_API_KEY): the running
# server reads the env once at startup, so any key change requires a
# restart. This script kills any stale uvicorn process bound to the
# default port and starts a fresh one in the background.
#
# Usage:
#   bash scripts/restart_server.sh             # default host/port (127.0.0.1:8000)
#   bash scripts/restart_server.sh 0.0.0.0 8001
set -euo pipefail

HOST="${1:-127.0.0.1}"
PORT="${2:-8000}"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="$PROJECT_ROOT/.venv/bin/python"

if [[ ! -x "$VENV_PY" ]]; then
  echo "error: $VENV_PY not found. Activate the venv or run 'python3.11 -m venv .venv' first." >&2
  exit 1
fi

# Kill any uvicorn process holding the port, give it a moment to
# release, then bail if something else is still listening.
pkill -f "uvicorn backend.main" 2>/dev/null || true
sleep 1
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -1 | grep -q LISTEN; then
  echo "error: port $PORT still in use after pkill. Investigate manually." >&2
  exit 1
fi

# Start the server in the background. Logs go to stderr; errors will
# surface immediately if the .env is malformed or the venv is broken.
cd "$PROJECT_ROOT"
nohup "$VENV_PY" -m uvicorn backend.main:app \
  --host "$HOST" --port "$PORT" --log-level warning \
  > /tmp/chronos_uvicorn.log 2>&1 &
SERVER_PID=$!

# Wait briefly for the server to come up, then probe /api/health so
# the operator sees whether Gemini is healthy after the restart.
sleep 3
if ! curl -sS --max-time 4 "http://${HOST}:${PORT}/api/health" >/tmp/_health.json 2>/dev/null; then
  echo "warn: server started (pid $SERVER_PID) but /api/health did not respond. Tail /tmp/chronos_uvicorn.log to investigate."
  exit 0
fi

echo "server up at http://${HOST}:${PORT}/ (pid $SERVER_PID)"
"$VENV_PY" -c '
import json, sys
d = json.load(open("/tmp/_health.json"))
g = d.get("gemini")
detail = d.get("gemini_detail", "")
if g is True:
    print("  gemini: OK", f"({detail})" if detail else "")
else:
    print("  gemini: NOT OK")
    print("    detail:", detail or "(none)")
    print("    -> the game will run with NoOp prose ('"'"'...'"'"') until the key is fixed.")
'
