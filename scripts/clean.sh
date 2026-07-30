#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "Cleaning development artifacts..."

# Remove virtual environment
# Don't activate .venv in clean.sh — we're about to delete it
if [ -d ".venv" ]; then
    rm -rf .venv
fi

# Remove test data
if [ -d "data/test" ]; then
    rm -rf data/test
fi

# Remove dev data
if [ -d "data/dev" ]; then
    rm -rf data/dev
fi

# Remove Python artifacts
find . -name "*.pyc" -delete 2>/dev/null || true
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Remove test results
rm -rf .pytest_cache
rm -rf htmlcov
rm -rf .coverage

echo "Cleanup complete!"
