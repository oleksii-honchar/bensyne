#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Use venv Python directly (required)
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
    echo "ERROR: .venv not found or incomplete. Run: ./scripts/setup.sh"
    exit 1
fi

export PYTHONPATH="./src:${PYTHONPATH:-}"

# Run pytest
echo "Running tests..."
"$VENV_PYTHON" -m pytest src/tests/ -v
