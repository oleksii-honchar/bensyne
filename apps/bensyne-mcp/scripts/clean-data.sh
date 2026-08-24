#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Mirror bensyne's resolve_data_dir() (src/infrastructure/config/data_dir.py):
#   1. DATA_DIR environment variable, else 2. ./data (relative to CWD).
# Override the root if your install points elsewhere, e.g.:
#   DATA_DIR=/data clean-data.sh <bank>
DATA_DIR="${DATA_DIR:-data}"

# v2 uniform bank layout (DEC-0062/U11, DEC-0064/U14):
#   All of a bank's data lives in ONE directory under the banks root:
#     {DATA_DIR}/banks/{bank}/
#       - mnemosyne.db
#       - file_metadata.db
#       - hash_index.db
#   (see src/infrastructure/bank/router.py — path authority)
#
# Usage:
#   clean-data.sh            → remove the entire DATA_DIR
#   clean-data.sh <bank>     → remove {DATA_DIR}/banks/<bank>
#
# The previous "all three locations" per-bank logic (data/<subdir>/banks/<bank>,
# data/<subdir>/<bank>, data/<bank>) matched the pre-v2 split layout and no
# longer matches where bensyne stores banks. It is intentionally removed.

if [ "${1:-}" != "" ]; then
    BANK="$1"
    BANK_PATH="$DATA_DIR/banks/$BANK"
    rm -rf "$BANK_PATH"
    echo "Removed bank '$BANK' from: $BANK_PATH"
else
    rm -rf "$DATA_DIR"
    echo "Removed $DATA_DIR/"
fi

echo "Data cleanup complete!"
