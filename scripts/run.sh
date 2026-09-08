#!/usr/bin/env bash
# Halite — run the TUI.
# Usage: ./scripts/run.sh [--debug]
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON=".venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    echo "[run.sh] No .venv found. Creating it with uv..." >&2
    uv venv --python python3.11 .venv
    uv pip install --python "$PYTHON" -r requirements.txt
fi

if [ "${1:-}" = "--debug" ]; then
    exec "$PYTHON" -m halite --debug
else
    exec "$PYTHON" -m halite
fi
