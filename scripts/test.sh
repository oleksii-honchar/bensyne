#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Activate virtual environment (required)
if [ ! -d ".venv" ]; then
    echo "ERROR: .venv not found. Run: ./scripts/setup.sh"
    exit 1
fi
source .venv/bin/activate

export PYTHONPATH="./src:${PYTHONPATH:-}"

# Run pytest
echo "Running tests..."
python -m pytest src/tests/ -v
