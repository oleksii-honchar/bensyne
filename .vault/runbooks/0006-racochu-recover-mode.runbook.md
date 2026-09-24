---
type: runbook
system: racochu
title: "Racochu Recover Mode (--recover)"
createdAt: "2026-08-26T07:18:26Z"
updatedAt: "2026-09-07T13:05:59Z"
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

## Notes on Auto-Population and Stub Repair

- **Auto-population on startup:** When racochu starts in watch mode (default), it automatically
  processes all existing files in watched sources to populate the Mnemosyne database. This means
  new installations or after a database wipe, simply starting racochu will seed all existing files.
- **Resume verification fix:** Running `racochu --resume` now includes verification that detects
  and repairs stub rows (incomplete file tracker entries). Files with missing or partial chunk
  records are automatically re-processed, so manual intervention for stub row issues is no longer
  required.

## Steps

1. (Optional) Dry-run first: `racochu --recover --dry-run` — reports the repair set without
   submitting.
2. Run recovery: `racochu --recover` (all sources) or `racochu --recover -s <sourceId>` (one
   source).
3. (Batch, non-session banks) Run `bash apps/racochu/scripts/recover-all-banks.sh
   [racochu_binary]` — iterates `--recover --source <id>` over every non-`agent-sessions_*`
   source in `~/.config/racochu.yaml`, prints a per-source ✓/✗ summary, and exits 1 if any
   source failed.
4. Watch the per-file outcomes: `reingested` (add/change), `repaired` (chunk-set submitted with
   `force_reembed: true`), `healthy`, `dry-run`, `skipped-missing-on-disk` / `skipped-filtered`,
   or `error`.
5. Recover waits for the processing queue to drain, then exits (no watch).

## Verification

- Untracked/new files are never processed (DB-tracked only).
- Every recover-pass file is re-submitted: `repairSet = expectedChunks` (the full chunk set,
  ADR-11 fix `a17e865`). The local verification pass stays CPU-only (`skipEnrichment`).
- Each repair submit takes the dedup path: the ADR-11 content-sync update refreshes memory text
  (no duplicate embeddings); `force_reembed` re-embeds only when the dedup target memory is
  missing (ADR-8).
- The enriched re-chunk pass costs an LLM call only for enrichment-enabled sources (default:
  disabled — DEC-0047).

## Rollback / Caveats

- ⚠️ Recover exits `0` even when every file errored (e.g. `getFileChunks` missing) — review
  medium finding; check logs for per-file errors before trusting the exit code.
- `contentHash` is parsed but no longer load-bearing — with `repairSet = expectedChunks`, any
  stored-chunk content drift is repaired by the re-submit (review low finding closed by `a17e865`).
- Stale chunks (present but no longer in the current chunk set) are NOT cleaned up in v1 —
  additive recovery only.
