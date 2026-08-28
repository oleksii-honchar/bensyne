#!/usr/bin/env bash
# reprocess-personas.sh — Re-ingest ONLY the agent-persona sources (the persona
# decision-tree banks) against the running Mnemosyne MCP server.
#
# Why this exists: after the AgentPersonaChunkingStrategy edge fix (expandHome
# resolving the `~` tree root), persona banks must be re-chunked so their
# decision_next / folder_hierarchy edges are materialized into file_relations.
# This targets ONLY persona sources and leaves non-persona sources (e.g.
# agent-sessions) untouched.
#
# How it works:
#   1. Optionally rebuilds dist and/or kills a running racochu (to avoid DB
#      lock contention) — both opt-in via flags.
#   2. Writes a temporary persona-only config (yq-filtered from the live config).
#   3. Runs a one-shot force-reprocess via `dotenvx run` (so LLM_API_KEY for
#      enrichment is loaded from the local .env) with --process-only.
#   4. Prints the resulting file_relations count per persona bank.
#
# Usage:
#   scripts/reprocess-personas.sh                   # reprocess all persona sources
#   scripts/reprocess-personas.sh --source <id>     # reprocess a single persona source
#   scripts/reprocess-personas.sh --build           # rebuild dist before running
#   scripts/reprocess-personas.sh --kill-running    # kill a running racochu first
#
# Environment overrides:
#   RACOCHU_CONFIG  Path to the source racochu.yaml (default: ~/.config/racochu.yaml)
#   BANKS_DIR       Where the MCP server stores per-bank DBs (default: ../bensyne-mcp/data/banks)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

SRC_CONFIG="${RACOCHU_CONFIG:-$HOME/.config/racochu.yaml}"
BANKS_DIR="${BANKS_DIR:-$PROJECT_DIR/../bensyne-mcp/data/banks}"
TMP_CONFIG="$(mktemp /tmp/racochu-personas.XXXXXX.yaml)"
trap 'rm -f "$TMP_CONFIG"' EXIT

DO_BUILD=0
KILL_RUNNING=0
SOURCE_ID=""

# ── parse args ──────────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
  case "$1" in
    --build)        DO_BUILD=1; shift ;;
    --kill-running) KILL_RUNNING=1; shift ;;
    --source)       SOURCE_ID="$2"; shift 2 ;;
    -h|--help)
      # Print the leading doc block (up to, not including, the `set -euo` line).
      awk '/^set -euo pipefail/{exit} {print}' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1 (see --help)" >&2
      exit 2
      ;;
  esac
done

# ── 1. build (opt-in) ───────────────────────────────────────────────────────
if [ "$DO_BUILD" -eq 1 ]; then
  echo "==> Building dist..."
  npm run build
fi

if [ ! -f dist/src/main.js ]; then
  echo "ERROR: dist/src/main.js not found. Build first (npm run build or --build)." >&2
  exit 1
fi

# Sanity: is the expandHome edge fix present in the built strategy?
if ! grep -q "expandHome" dist/src/application/strategies/agent-persona-chunking.strategy.js 2>/dev/null; then
  echo "WARN: 'expandHome' not found in the built strategy — dist may be stale and" >&2
  echo "      edges may not be generated. Rebuild with: scripts/reprocess-personas.sh --build" >&2
fi

# ── 2. kill a running racochu (opt-in) ──────────────────────────────────────
if [ "$KILL_RUNNING" -eq 1 ]; then
  echo "==> Killing any running racochu instance..."
  node scripts/kill-stale-racochu.mjs
fi

# ── 3. build persona-only config ────────────────────────────────────────────
if [ ! -f "$SRC_CONFIG" ]; then
  echo "ERROR: source config not found at $SRC_CONFIG (set RACOCHU_CONFIG to override)." >&2
  exit 1
fi

if [ -n "$SOURCE_ID" ]; then
  # Keep only the requested source.
  yq eval "del(.watchSources[] | select(.id != \"$SOURCE_ID\"))" "$SRC_CONFIG" > "$TMP_CONFIG"
else
  # Keep only persona sources (id prefix "agent-persona-").
  yq eval 'del(.watchSources[] | select(.id | test("^agent-persona-") | not))' "$SRC_CONFIG" > "$TMP_CONFIG"
fi

KEPT="$(yq eval '.watchSources[].id' "$TMP_CONFIG" | tr '\n' ' ')"
echo "==> Persona-only config written to: $TMP_CONFIG"
echo "    sources: ${KEPT}"

# ── 4. run one-shot force-reprocess (dotenvx loads LLM_API_KEY from .env) ───
echo "==> Running one-shot force-reprocess (--process-only)..."
if [ -n "$SOURCE_ID" ]; then
  npx dotenvx run -- node dist/src/main.js --force-reprocess --process-only -c "$TMP_CONFIG" --source "$SOURCE_ID"
else
  npx dotenvx run -- node dist/src/main.js --force-reprocess --process-only -c "$TMP_CONFIG"
fi

# ── 5. report file_relations per persona bank ───────────────────────────────
echo ""
echo "==> file_relations after re-ingest (from $BANKS_DIR):"
if [ -d "$BANKS_DIR" ]; then
  found_any=0
  for bank_dir in "$BANKS_DIR"/persona_*; do
    [ -d "$bank_dir" ] || continue
    bank="$(basename "$bank_dir")"
    found_any=1
    db="$bank_dir/file_metadata.db"
    if [ -f "$db" ]; then
      fr="$(sqlite3 "$db" "SELECT COUNT(*) FROM file_relations;" 2>/dev/null || echo '?')"
      fc="$(sqlite3 "$db" "SELECT COUNT(*) FROM files;" 2>/dev/null || echo '?')"
      echo "    $bank: files=$fc  file_relations=$fr"
    else
      echo "    $bank: (no file_metadata.db)"
    fi
  done
  [ "$found_any" -eq 0 ] && echo "    (no persona_* bank directories found)"
else
  echo "    (BANKS_DIR does not exist: $BANKS_DIR)"
fi

echo ""
echo "Done."
