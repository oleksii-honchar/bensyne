#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Wipe runtime data under data/ (watcher DB and scan state).

DATA_DIR="data"

if [ -d "$DATA_DIR" ]; then
    rm -rf "$DATA_DIR"
    echo "Removed $DATA_DIR/"
else
    echo "$DATA_DIR/ does not exist — nothing to clean."
fi

echo "Data cleanup complete!"
