---
type: memory
title: "forgetFile FILE_NOT_FOUND Is an Idempotent No-Op — Server Returns JSON Status"
createdAt: "2026-08-28T17:23:01Z"
updatedAt: "2026-08-28T17:23:01Z"
system: shared
tags: [bensyne, racochu, forget, mcp-contract, gotcha]
see_also:
  - decisions/0098-forgetfile-file-not-found-json-status.decision.md
  - decisions/0099-forgetbyfile-error-wrapped-fallback.decision.md
  - memories/0021-bensyne-forgetfile-tombstone.memory.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Memory: forgetFile FILE_NOT_FOUND Is an Idempotent No-Op — Server Returns JSON Status

## Fact

`forgetFile` on a path with no file row in the bensyne DB is a **legitimate
business state**, not an error: the server returns
`{"status": "FILE_NOT_FOUND"}` as a JSON tool result (since DEC-0099), and the
racochu client treats it as an idempotent no-op — no retries, no `ERROR` log.

## Context

Discovered in the 2026-08-28 racochu log-error investigation. Before the fix,
the server raised `ValidationError` → FastMCP wrapped it in
`{text: "Error calling tool 'forgetFile': ... FILE_NOT_FOUND ..."}` → the
client's `status`-only success check missed it → 3× retry storm +
`ERROR: Failed to forget file after 3 retries` on every change/delete event
for a file with no DB row. File rows are broadly missing for `agent-sessions`
after the 2026-08-24 mass-forget recovery backfill (memories re-ingested
without file rows), so this was frequent.

## Impact

- `forgetByFile` on unknown paths is now silent (debug-level) and fast — no
  retries.
- Distinguish from [[0021-bensyne-forgetfile-tombstone]]: that memory covers
  the DELETED **tombstone** facet (row exists, marked deleted); this memory
  covers the **missing row** facet (no row at all → `FILE_NOT_FOUND`).
- TTL sweep (DEC-0073) also benefits: fewer retry storms on unknown-file
  rows.
