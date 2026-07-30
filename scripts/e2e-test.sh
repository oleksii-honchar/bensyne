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

# Set test environment (respect existing env vars)
export PYTHONPATH="./src:${PYTHONPATH:-}"
export PYTHONUNBUFFERED=1

# Use a unique port for e2e tests (respects env vars)
E2E_PORT="${E2E_PORT:-3001}"
E2E_DATA_DIR="${E2E_DATA_DIR:-./data/e2e-test}"

# Create test data directory
mkdir -p "$E2E_DATA_DIR"

# Start server in background using main.py (activated venv python)
echo "Starting test server on port $E2E_PORT..."
.venv/bin/python main.py --port "$E2E_PORT" --data-dir "$E2E_DATA_DIR" &
SERVER_PID=$!

# Function to cleanup on exit
cleanup() {
    echo "Stopping server (PID: $SERVER_PID)..."
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
    echo "Cleaning up test data..."
    rm -rf "$E2E_DATA_DIR"
}
trap cleanup EXIT

# Wait for server to be ready (poll /health)
echo "Waiting for server to be ready..."
for i in $(seq 1 60); do
    if curl -sf "http://127.0.0.1:$E2E_PORT/health" > /dev/null 2>&1; then
        echo "Server is ready (PID: $SERVER_PID)"
        break
    fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "Server process died unexpectedly"
        exit 1
    fi
    sleep 0.5
done

if ! curl -sf "http://127.0.0.1:$E2E_PORT/health" > /dev/null 2>&1; then
    echo "Server failed to start within 30s"
    exit 1
fi

# Run e2e tests
echo "Running end-to-end tests..."
pytest src/tests/e2e/ -v --tb=short

TEST_RESULT=$?

# Cleanup is handled by trap
exit "$TEST_RESULT"
