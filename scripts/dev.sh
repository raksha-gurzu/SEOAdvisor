#!/usr/bin/env bash
# Start the backend (:8420) and the web app (:4280) together. Ctrl+C stops both.
#   make dev        (or: scripts/dev.sh)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT=8420
WEB_PORT=4280
cd "$ROOT"

fail() { echo "error: $*" >&2; exit 1; }

[[ -x .venv/bin/uvicorn ]] || fail "no Python environment. Run: python3.12 -m venv .venv && .venv/bin/pip install -e \".[dev]\""
[[ -f .env ]] || fail "no .env file. Run: cp .env.example .env, then add your keys"
command -v npm >/dev/null || fail "npm is not installed (needed for the web app)"
for port in $BACKEND_PORT $WEB_PORT; do
  if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
    fail "port $port is already in use. Is the app already running?"
  fi
done
if [[ ! -d web/node_modules ]]; then
  echo "Installing web packages (first run only)..."
  (cd web && npm install --no-fund --no-audit)
fi

backend_pid=""
stop() {
  trap - EXIT INT TERM
  [[ -n "$backend_pid" ]] && kill "$backend_pid" 2>/dev/null && wait "$backend_pid" 2>/dev/null
  echo
  echo "Stopped."
}
trap stop EXIT
trap 'stop; exit 0' INT TERM  # Ctrl+C is the normal way to stop: not an error

echo "Starting the backend on :$BACKEND_PORT..."
.venv/bin/uvicorn seo_engine.api.app:app --reload --port "$BACKEND_PORT" --log-level warning &
backend_pid=$!

for _ in $(seq 1 60); do  # wait up to 30 s for the backend to answer
  if (exec 3<>"/dev/tcp/127.0.0.1/$BACKEND_PORT") 2>/dev/null; then break; fi
  kill -0 "$backend_pid" 2>/dev/null || fail "the backend did not start (see the error above)"
  sleep 0.5
done

echo
echo "  SEO Advisor is running: http://localhost:$WEB_PORT"
echo "  Press Ctrl+C to stop."
echo
cd web
npm run dev -- --clearScreen false
