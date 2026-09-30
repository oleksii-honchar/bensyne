#!/usr/bin/env bash
# reprocess-edges.sh — Re-process edges (ghost edge detection + pruning) for
# all watch sources or a specific source.
#
# Usage:
#   scripts/reprocess-edges.sh                   # all sources
#   scripts/reprocess-edges.sh --source <id>     # specific source
#   scripts/reprocess-edges.sh --passes 3        # run N passes (default 3)
#   scripts/reprocess-edges.sh --build           # rebuild dist first
#
# The edge reprocessing process:
# 1. Builds a file ID map for all files in the source (pass 1)
# 2. For each file, calls expand_file_relations to get its edges
# 3. Validates each target file ID resolves to a real file
# 4. Calls prune_phantom_edge_stub for any ghost edges
#
# Multiple passes may be needed because pruning in one pass can expose
# additional ghost edges in the next pass.
#
# Environment overrides:
#   RACOCHU_CONFIG  Path to the racochu config file

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

SRC_CONFIG="${RACOCHU_CONFIG:-$HOME/.config/racochu.yaml}"
DO_BUILD=0
SOURCE_ID=""
PASSES=3

# Parse args
while [ $# -gt 0 ]; do
  case "$1" in
    --build)        DO_BUILD=1; shift ;;
    --source)       SOURCE_ID="$2"; shift 2 ;;
    --passes)       PASSES="$2"; shift 2 ;;
    -h|--help)
      awk '/^set -euo pipefail/{exit} {print}' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1 (see --help)" >&2
      exit 2
      ;;
  esac
done

# Build if requested
if [ "$DO_BUILD" -eq 1 ]; then
  echo "==> Building dist..."
  npm run build
fi

if [ ! -f dist/src/main.js ]; then
  echo "ERROR: dist/src/main.js not found. Build first (npm run build or --build)." >&2
  exit 1
fi

if [ ! -f "$SRC_CONFIG" ]; then
  echo "ERROR: source config not found at $SRC_CONFIG (set RACOCHU_CONFIG to override)." >&2
  exit 1
fi

# Log file for full output
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="logs/reprocess-edges-${TIMESTAMP}.log"
mkdir -p logs
echo "==> Running edge reprocessing ($PASSES passes)..."
echo "    Full log: $LOG_FILE"

for pass in $(seq 1 $PASSES); do
  echo ""
  echo "=== Pass $pass/$PASSES ==="

  if [ -n "$SOURCE_ID" ]; then
    echo "    source: $SOURCE_ID"
    npx dotenvx run -- node dist/src/main.js --force-reprocess --process-only --reprocess-edges -c "$SRC_CONFIG" --source "$SOURCE_ID" 2>&1 | tee -a "$LOG_FILE" | grep -E "ghostEdgesFound|Failed to prune|Edge reprocessing complete|Processing file \["
  else
    echo "    sources: all"
    npx dotenvx run -- node dist/src/main.js --force-reprocess --process-only --reprocess-edges -c "$SRC_CONFIG" 2>&1 | tee -a "$LOG_FILE" | grep -E "ghostEdgesFound|Failed to prune|Edge reprocessing complete|Processing file \["
  fi
done

echo ""
echo "Done."
