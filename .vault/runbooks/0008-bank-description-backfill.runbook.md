---
type: runbook
title: "Bank Description Backfill"
createdAt: "2026-08-28T12:58:00Z"
updatedAt: "2026-08-28T12:58:00Z"
system: bensyne-mcp
tags: [mcp, operator, bank-discovery, idempotency]
see_also:
  - decisions/0096-bank-description-backfill-via-operator-script.decision.md
  - memories/0025-channel-weighting-makes-description-backfill-load-bearing.memory.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Runbook: Bank Description Backfill

## Prerequisites

- Bensyne MCP server reachable (default port via `main.py`).
- OpenCode runtime's MCP client configured for the Bensyne namespace.
- Shell access to the host where `apps/bensyne-mcp/` lives.

## Steps

1. **Verify which banks need backfill.** From `apps/bensyne-mcp/`,
   invoke `listMemoryBanks` over MCP and inspect `description`
   for `agent-sessions` and `vault`:

   ```bash
   cd apps/bensyne-mcp
   .venv/bin/python -c "
   import asyncio
   # Use your MCP client of choice to call listMemoryBanks,
   # then check description for 'agent-sessions' and 'vault'.
   "
   ```

   Expected pre-backfill state: `agent-sessions.description == ""`
   and `vault.description == ""`.

2. **Dry-run the script.** `scripts/backfill-bank-descriptions.sh
   --help` should print a banner with usage. `scripts/backfill-bank-descriptions.sh`
   without `--force` should print what it would write and refuse to
   overwrite any non-empty description.

3. **Run the backfill.**

   ```bash
   cd apps/bensyne-mcp
   ./scripts/backfill-bank-descriptions.sh
   ```

   The script:
   - Calls `listMemoryBanks` for the current descriptions.
   - For `agent-sessions` and `vault`, if the description is empty,
     calls `registerMemoryBank(name=..., description=...)` with the
     canonical copy (see `decisions/0096-...` for the exact wording).
   - Refuses to overwrite a non-empty description without
     `--force`.
   - Exits 0 on success.

4. **Verify the backfill.** Re-run `listMemoryBanks`; confirm
   `agent-sessions.description` and `vault.description` now contain
   the canonical copy.

## Verification

- `listMemoryBanks` returns non-empty descriptions for both banks.
- `searchMemoryBank(query="vault architecture ADR")` returns
  `vault` in `matches` with `score > 0`.
- `searchMemoryBank(query="session history decisions")` returns
  `agent-sessions` in `matches` with `score > 0`.
- Drift gate (`tests/test_skills/test_skill_text_drift.py`) still
  passes (skill text unchanged by the backfill).

## Rollback

If the backfilled description is wrong, run:

```bash
./scripts/backfill-bank-descriptions.sh --force
```

…with the corrected description in the script. The script does
NOT auto-run on boot, so a re-run is the only rollback path. There
is no data loss — `registerMemoryBank` overwrites the description
string only.

If the backfill introduced a regression in search ranking (e.g.
a term now over-matches), revert the script to its pre-ship version
or pass `--force` with an empty description to clear the bank.