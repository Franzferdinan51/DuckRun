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
if [[ "$(uname)" == "Darwin" && "$(uname -m)" == "arm64" ]]; then
  # Apple Silicon: also install the MLX extra so the mlx backend works out of the box.
  pip install -q -e ".[mlx]" 2>/dev/null || pip install -q -r requirements.txt
else
  pip install -q -e . 2>/dev/null || pip install -q -r requirements.txt
fi

echo "[duckrun] starting..."
exec python -m duckrun "$@"
