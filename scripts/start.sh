#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Activate virtual environment
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Set development environment variables
export MNEMOSYNE_DATA_DIR="./data/dev"
export PYTHONPATH="./src:${PYTHONPATH:-}"
export PYTHONUNBUFFERED=1

# Create data directory
mkdir -p "$MNEMOSYNE_DATA_DIR"

# Start server using main.py
echo "Starting better-mnemosyne server..."
echo "Data directory: $MNEMOSYNE_DATA_DIR"
echo "Press Ctrl+C to stop"

python3.12 main.py --port 3000 --log-level INFO
