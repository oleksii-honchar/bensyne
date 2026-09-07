#!/bin/bash
# Run racochu recover on all sources (excluding agent-sessions)
# Usage: ./recover-all-banks.sh [racochu_binary]
#
# Default racochu binary: node dist/src/main.js (from this repo's build)
# Pass an alternative path as $1 if needed.
# Reads source IDs from ~/.config/racochu.yaml.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
RACOCHU="${1:-node $APP_DIR/dist/src/main.js}"
CONFIG="${RACOCHU_CONFIG:-$HOME/.config/racochu.yaml}"

ts() { date '+%H:%M:%S'; }

echo "[$(ts)] Using racochu: $RACOCHU"
echo "[$(ts)] Config: $CONFIG"
echo ""

# Read source IDs from config, skip agent-sessions_*
SOURCES=$(grep "^  - id:" "$CONFIG" | sed 's/  - id: //' | grep -v "^agent-sessions_" || true)

if [ -z "$SOURCES" ]; then
    echo "[$(ts)] No sources found (excluding agent-sessions). Exiting."
    exit 0
fi

echo "[$(ts)] Sources to recover:"
echo "$SOURCES" | while read -r s; do echo "  - $s"; done
echo ""

FAILED=0
SUCCESS=0

while IFS= read -r source_id; do
    echo ""
    echo "[$(ts)] ======================================="
    echo "[$(ts)] Recovering: $source_id"
    echo "[$(ts)] ======================================="
    
    set +e
    $RACOCHU --recover --source "$source_id" 2>&1
    exit_code=$?
    set -e
    
    if [ $exit_code -eq 0 ]; then
        echo "[$(ts)]   ✓ OK"
        SUCCESS=$((SUCCESS + 1))
    else
        echo "[$(ts)]   ✗ FAILED (exit code: $exit_code)"
        FAILED=$((FAILED + 1))
    fi
done <<< "$SOURCES"

echo ""
echo "[$(ts)] ======================================="
echo "[$(ts)] Done. Success: $SUCCESS, Failed: $FAILED"
echo "[$(ts)] ======================================="
[ $FAILED -eq 0 ] || exit 1
