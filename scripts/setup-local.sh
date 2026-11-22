#!/usr/bin/env bash
# One-time setup for running directly on Linux/macOS (no Docker).
#   bash scripts/setup-local.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Checking tools"
command -v python3 >/dev/null || { echo "Python 3.11+ is required"; exit 1; }
command -v node >/dev/null || { echo "Node.js 20+ is required"; exit 1; }
python3 --version; node --version

echo "==> Backend"
cd "$ROOT/icbOfficerAssoAPI"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt

echo "==> Frontend"
cd "$ROOT/icbOfficerAssoUI"
npm install

cd "$ROOT"
[ -f .env ] || { cp .env.example .env; echo "==> Created .env from .env.example"; }
mkdir -p data/Scanned data/Completed data/Failed data/Previews

echo
echo "Setup complete. Start with:  bash scripts/start-local.sh"
