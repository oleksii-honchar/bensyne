---
type: runbook
title: "Delete a Redundant Memory Bank"
createdAt: "2026-09-16T10:45:00Z"
updatedAt: "2026-09-16T10:45:00Z"
system: bensyne-mcp
tags: [mcp, operator, bank-registry, sqlite, cleanup]
see_also:
  - runbooks/0008-bank-description-backfill.runbook.md
  - concepts/0027-bank-naming-contract.concept.md
  - decisions/0062-persistent-bank-registry.decision.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Runbook: Delete a Redundant Memory Bank

## Prerequisites

- Shell access to the host running the Bensyne MCP server (e.g. puma.lan,
  docker container `bensyne-mcp`, volume `./data:/data`).
- The exact bank name to remove (registry rows are keyed on `name`).
- Confirmation the bank is redundant: `memory_count == 0` and no
  racochu `watchSource` / code path registers it (otherwise it will
  be re-created on next registration).

## Steps

1. **Verify redundancy** — call `listMemoryBanks` (or `searchMemoryBank`)
   and check the target row: status `registered`, `memory_count == 0`.
   Cross-check `~/.config/racochu.yaml` watchSources and the codebase for
   any reference to the name. A typo'd/orphan name (e.g. `obisidian_olho`
   vs the real `obsidian_olho`) is the common case.

2. **Delete the registry row** — there is **no MCP delete-bank tool**
   (`MemoryBankRepository.delete()` exists at
   `src/infrastructure/bank/memory_bank_repository.py:263` but is **not
   wired** to any tool). Delete directly in SQL on the host:

   ```bash
   # host side (compose dir): data dir volume ./data
   sqlite3 data/memory_banks.db "DELETE FROM memory_banks WHERE name='<bank>';"

   # or, from inside the container without sqlite3 CLI
   docker exec bensyne-mcp python -c "
   import sqlite3
   DB='/data/memory_banks.db'
   con=sqlite3.connect(DB)
   con.execute(\"DELETE FROM memory_banks WHERE name='<bank>';\")
   con.commit()
   print(con.execute(\"SELECT changes()\").fetchone()[0], 'row(s) deleted')
   "
   ```

   No server restart is needed — the registry is read live per call.

3. **Check for the bank data dir** — a bank with 0 memories that was only
   `registerMemoryBank`-ed has **no** `data/banks/<bank>/` directory
   (created lazily on first memory). If the directory exists, remove it
   too (it holds the bank's DBs).

## Verification

- `listMemoryBanks` no longer lists the bank.
- `searchMemoryBank` returns no match for the old name.
- Any real vault with a similar name (e.g. `obsidian_olho`) is untouched
  and still `active` with its memories intact.

## Rollback

- **Registry row:** re-register with
  `registerMemoryBank(name="<bank>", description="...")` — the
  `ON CONFLICT DO UPDATE` upsert recreates the row.
- **Bank data dir:** if it was deleted, memory DBs are gone; restore from
  backup if available. Deleting is irreversible for the per-bank DB files.

## Notes

- Practice observed 2026-09-16: the orphan `obisidian_olho` row (typo of
  `obsidian_olho`, 0 memories) was removed this way on puma.lan; the real
  vault kept its 5923 memories.