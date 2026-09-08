#!/usr/bin/env bash
# Halite launcher — runs the Ink-based inline TUI.
# Usage: ./scripts/run.sh [--debug]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INK_DIR="${PROJECT_ROOT}/halite/ui/ink"

# If the Ink build is missing, build it
if [ ! -f "${INK_DIR}/dist/index.js" ]; then
    echo "Ink TUI not built — building..."
    (cd "${INK_DIR}" && npm install && npm run build)
fi

# Launch the Ink TUI (Node is the parent; it spawns the Python backend)
export HALITE_ROOT="${PROJECT_ROOT}"
cd "${PROJECT_ROOT}"
exec node "${INK_DIR}/dist/index.js" "$@"