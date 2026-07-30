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

python main.py --port 3000 --data-dir "$MNEMOSYNE_DATA_DIR" --log-level INFO
