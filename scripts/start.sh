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

# Load .env file if it exists (respects env vars already set)
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
    echo "Loaded .env file"
fi

# Set development environment variables (respect existing env vars)
export MNEMOSYNE_DATA_DIR="${MNEMOSYNE_DATA_DIR:-./data/dev}"
export PYTHONPATH="./src:${PYTHONPATH:-}"
export PYTHONUNBUFFERED=1

# Create data directory
mkdir -p "$MNEMOSYNE_DATA_DIR"

# Kill any existing processes on the target port
TARGET_PORT="${PORT:-3000}"
EXISTING_PID=$(lsof -ti ":${TARGET_PORT}" 2>/dev/null || true)
if [ -n "$EXISTING_PID" ]; then
    echo "Killing existing process on port $TARGET_PORT (PID: $EXISTING_PID)..."
    kill "$EXISTING_PID" 2>/dev/null || true
    sleep 1
fi

# Start server using main.py (env vars provide defaults, CLI overrides)
echo "Starting Bensyne server..."
echo "Data directory: $MNEMOSYNE_DATA_DIR"
echo "Press Ctrl+C to stop"

.venv/bin/python main.py --port "$TARGET_PORT" --data-dir "$MNEMOSYNE_DATA_DIR"
