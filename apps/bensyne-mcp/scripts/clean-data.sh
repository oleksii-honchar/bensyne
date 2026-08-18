#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Wipe runtime bank data under data/.
#
# NOTE: bank state is split across multiple locations:
#   data/{DATA_SUBDIR}/banks/{bank}/ → mnemosyne.db
#   data/{DATA_SUBDIR}/{bank}/       → file_metadata.db
#   data/{bank}/                     → hash_index.db
#                                       (HashIndexService falls back to
#                                       CWD-relative Path("data")/{bank} —
#                                       see src/infrastructure/mcp/hash_index_service.py:144)
#
# Usage:
#   clean-data.sh            → remove the entire data/ directory
#   clean-data.sh <bank>     → remove that bank's dirs in all three locations
#   clean-data.sh <bank> <data-subdir> → limit per-bank dirs to data/<data-subdir>/
#                                        (e.g.: clean-data.sh tmp-vault dev)

DATA_DIR="data"

if [ "${1:-}" != "" ]; then
    BANK="$1"
    SUBDIR="${2:-dev}"
    rm -rf "$DATA_DIR/$SUBDIR/banks/$BANK" "$DATA_DIR/$SUBDIR/$BANK" "$DATA_DIR/$BANK"
    echo "Removed bank '$BANK' from: data/$SUBDIR/banks/$BANK, data/$SUBDIR/$BANK, data/$BANK"
else
    rm -rf "$DATA_DIR"
    echo "Removed $DATA_DIR/"
fi

echo "Data cleanup complete!"
