#!/usr/bin/env bash
# Backfill bank descriptions for `agent-sessions` and `vault`.
#
# Per spec C9: register the two Racochu-managed source banks with curated
# descriptions so `searchMemoryBank` ranking and the schema-level
# "what banks exist" docs are accurate.
#
# Idempotent — running multiple times does not error. Pre-flight refuses to
# overwrite an existing bank description unless `--force` is passed.
#
# Usage:
#   ./scripts/backfill-bank-descriptions.sh [BASE_URL] [--force]
#
# Examples:
#   ./scripts/backfill-bank-descriptions.sh                          # dry-mode: refuses overwrite
#   ./scripts/backfill-bank-descriptions.sh --force                  # overwrite existing descriptions
#   ./scripts/backfill-bank-descriptions.sh http://localhost:3000    # custom base URL

set -euo pipefail

# ---------------------------------------------------------------------------
# Parse args
# ---------------------------------------------------------------------------

BASE_URL="${BENSYNE_BASE_URL:-http://localhost:3000}"
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --help|-h)
      sed -n '2,20p' "$0"
      exit 0
      ;;
    http://*|https://*) BASE_URL="$arg" ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Banks to backfill (name -> description).
# ---------------------------------------------------------------------------

AGENT_SESSIONS_DESC='Racochu-ingested session history from ~/.agent-sessions/ — prior decisions, handoffs, session context'
VAULT_DESC='Racochu-ingested vault knowledge from project .vault/ dirs — architecture, ADRs, runbooks'

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Send a single MCP JSON-RPC request to /mcp and print the parsed JSON
# response's "result" field. Errors out on transport or JSON-RPC errors.
_mcp_call() {
  local method="$1"
  local params_json="$2"
  local id="$3"
  local body
  body=$(jq -n --argjson id "$id" --arg method "$method" --argjson params "$params_json" \
    '{jsonrpc:"2.0", id:$id, method:$method, params:$params}')
  local resp
  resp=$(curl -sS -X POST "${BASE_URL}/mcp" \
    -H 'Content-Type: application/json' \
    -d "$body")
  local err
  err=$(echo "$resp" | jq -r '.error // empty')
  if [[ -n "$err" ]]; then
    echo "MCP error from $method: $err" >&2
    return 1
  fi
  echo "$resp" | jq -r '.result.structuredContent // .result'
}

# Get the live description for a bank via listMemoryBanks. Returns "" if
# the bank does not exist yet.
_get_existing_description() {
  local name="$1"
  local raw
  raw=$(_mcp_call "tools/call" '{"name":"listMemoryBanks","arguments":{}}' 1)
  echo "$raw" | jq -r --arg n "$name" \
    '.content[0].text | fromjson | .banks[] | select(.name == $n) | .description // ""' \
    2>/dev/null || echo ""
}

# Register a bank. Returns 0 on success, 1 on MCP error.
_register_bank() {
  local name="$1"
  local desc="$2"
  local args_json
  args_json=$(jq -n --arg n "$name" --arg d "$desc" '{name:$n, description:$d}')
  _mcp_call "tools/call" "$(jq -n --arg a "$args_json" '{name:"registerMemoryBank",arguments:$a}')" 2 \
    >/dev/null
}

# ---------------------------------------------------------------------------
# Backfill loop
# ---------------------------------------------------------------------------

backfill_one() {
  local name="$1"
  local desc="$2"
  local existing
  existing=$(_get_existing_description "$name")
  if [[ -z "$existing" ]]; then
    echo "[backfill] $name: not registered — registering"
    _register_bank "$name" "$desc"
    echo "[backfill] $name: registered"
    return 0
  fi
  if [[ "$existing" == "$desc" ]]; then
    echo "[backfill] $name: already has the canonical description (no-op)"
    return 0
  fi
  if [[ "$FORCE" -eq 1 ]]; then
    echo "[backfill] $name: existing description differs — overwriting (--force)"
    _register_bank "$name" "$desc"
    echo "[backfill] $name: overwritten"
    return 0
  fi
  echo "[backfill] $name: existing description differs; refusing to overwrite without --force" >&2
  echo "  existing: $existing" >&2
  echo "  target:   $desc" >&2
  return 1
}

FAIL=0
backfill_one "agent-sessions" "$AGENT_SESSIONS_DESC" || FAIL=1
backfill_one "vault"          "$VAULT_DESC"          || FAIL=1

if [[ "$FAIL" -ne 0 ]]; then
  echo "[backfill] one or more banks refused; re-run with --force to overwrite" >&2
  exit 1
fi

echo "[backfill] done"
