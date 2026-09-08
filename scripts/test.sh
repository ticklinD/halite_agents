#!/usr/bin/env bash
# Halite — run the test suite.
# Usage: ./scripts/test.sh [pytest args...]
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON=".venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    echo "[test.sh] No .venv found. Creating it with uv..." >&2
    uv venv --python python3.11 .venv
    uv pip install --python "$PYTHON" -r requirements.txt -r <(echo "pytest" "pytest-asyncio")
fi

exec "$PYTHON" -m pytest tests/ -q "$@"
