---
type: runbook
system: racochu
title: "Racochu Recover Mode (--recover)"
createdAt: "2026-08-26T07:18:26Z"
updatedAt: "2026-08-26T07:18:26Z"
tags: [runbook, recover, racochu, maintenance]
see_also:
  - specifications/0007-racochu-recover-mode.spec.md
  - decisions/0081-recover-exiting-cli-mode.decision.md
  - runbooks/0003-troubleshooting.runbook.md
---

# Runbook: Racochu Recover Mode (--recover)

## Prerequisites

- A bensyne-mcp deployment exposing the `getFileChunks` tool (deployment dependency — without
  it recover cannot verify).
- A racochu config with the `mcp.url` pointing at that deployment.

## Steps

1. (Optional) Dry-run first: `racochu --recover --dry-run` — reports missing chunks without
   submitting.
2. Run recovery: `racochu --recover` (all sources) or `racochu --recover -s <sourceId>` (one
   source).
3. Watch the per-file outcomes: `healthy — skip`, `reingested`, or repair-set submission with
   `force_reembed: true`.
4. Recover waits for the processing queue to drain, then exits (no watch).

## Verification

- Untracked/new files are never processed (DB-tracked only).
- Healthy files cost zero LLM calls; repair cost = 1 enrichment pass + embeddings for the
  missing set only.

## Rollback / Caveats

- ⚠️ Recover exits `0` even when every file errored (e.g. `getFileChunks` missing) — review
  medium finding; check logs for per-file errors before trusting the exit code.
- ⚠️ `contentHash` is parsed but not compared in the repair-set computation — a stored chunk
  with wrong content at a present index is treated as healthy (review low finding).
- Stale chunks (present but no longer in the current chunk set) are NOT cleaned up in v1 —
  additive recovery only.
