#!/usr/bin/env bash
# Starts API + UI in the foreground (Linux/macOS, no Docker).  Ctrl+C stops both.
#   bash scripts/start-local.sh            # development (hot reload)
#   bash scripts/start-local.sh --prod     # optimised build, for a server
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-dev}"

cd "$ROOT/icbOfficerAssoAPI"
if [ "$MODE" = "--prod" ]; then
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
else
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
fi
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT

cd "$ROOT/icbOfficerAssoUI"
echo "Admin panel:      http://localhost:3000/admin"
echo "Public dashboard: http://localhost:3000/dashboard"
if [ "$MODE" = "--prod" ]; then
  npm run build
  npm run start -- --hostname 0.0.0.0 --port 3000
else
  npm run dev -- --hostname 0.0.0.0 --port 3000
fi
