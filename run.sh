#!/usr/bin/env bash
# DuckRun dev runner: creates a venv on first run, installs deps, starts the server.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "[duckrun] creating venv..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "[duckrun] installing/updating deps..."
pip install -q -e . 2>/dev/null || pip install -q -r requirements.txt

echo "[duckrun] starting..."
exec python -m duckrun "$@"
