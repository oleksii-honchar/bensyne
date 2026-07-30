#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Use Python 3.12 explicitly
PYTHON=python3.12
if ! command -v "$PYTHON" &>/dev/null; then
    echo "ERROR: $PYTHON not found. Install or use pyenv (pyenv install 3.12)"
    exit 1
fi

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    "$PYTHON" -m venv .venv
fi

# Use venv's python directly (avoid PATH/activation issues)
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"

# Upgrade pip
"$VENV_PYTHON" -m pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
"$VENV_PYTHON" -m pip install -r requirements.txt

# Install dev dependencies
"$VENV_PYTHON" -m pip install pytest pytest-asyncio httpx black flake8 mypy

# Create test data directory
mkdir -p data/test

echo "Setup complete! Activate environment with: source .venv/bin/activate"
