---
type: runbook
system: racochu
title: "Verify the racochu Ingest Gate Is Holding (Post-Change Health Check)"
createdAt: "2026-11-01T13:54:35Z"
updatedAt: "2026-11-01T13:54:35Z"
tags: [racochu, verification, logs, deduplication, observability]
see_also:
  - decisions/0119-file-hash-ingest-gate-and-terminal-skip-quarantine.decision.md
  - decisions/0121-manual-cli-watch-operation-with-instance-lock.decision.md
  - runbooks/0003-troubleshooting.runbook.md
  - concepts/0020-file-hash-deduplication.concept.md
---

# Verify the racochu Ingest Gate Is Holding (Post-Change Health Check)

## Prerequisites

- A completed manual pass (watch start with auto-populate, or `racochu --resume`) since the
  DEC-0119 rollout.
- pino logs under `~/.local/share/racochu/logs/` and read access to the tracker DB
  `data/racochu.db` (query while no racochu process is running, or accept transient counts).

## Steps

1. **Read the batch summary** per pass:
   `resume finished: files=…, gated-skips=…, terminal-skip-skips=…, verified-skips=…, re-ingested=…`
   (emitted by `ForceReprocessService`). Repeat after a second start: unchanged corpus ⇒ the
   summary must stay flat with near-zero real work.
2. **Count gate activity** in current logs:
   `rg -c "Skipping unchanged file \(hash gate\)"` and `rg -c "terminal-skip-recorded reason="`.
   Re-runnable analyzers (build the per-file repeat histogram on any window):
   `~/.agent-sessions/26/10/31/261031-0953-bootstrap-researcher/materials/analyze-*.mjs`.
3. **DB sanity:**
   `SELECT COUNT(*) FROM FileTracker WHERE fileHash IS NULL;` must be non-increasing over time;
   `SELECT COUNT(*) FROM FileTracker WHERE skipReason IS NOT NULL;` ≈ stable (~ the
   never-ingestable set; expected ≈ 250 from the pre-change analysis — measure, don't assume).
4. **Repair-path sanity:** `Resuming stale-tracker file` events may still appear — that is the
   `forceIngest` repair working (DEC-0119 §Decision-4), not a gate failure.

## Verification

Healthy = `gated-skips` ≈ unchanged-file volume; follow-through `Chunks created` /
`File processed` for stable files ≈ 0 across repeated starts; `File processing failed`
`too_small` events = 0 (they are `terminal-skip-recorded` now); and the original user-visible
property holds — no repeated re-ingest of unchanged files over a 1-week window.

## Rollback / Escalation

- No rollback short of the designated override: `--force-reprocess [--source X]` (unconditional
  re-evaluation; also the escape hatch after filter-config changes per DEC-0119 consequences).
- If `gated-skips` ≈ 0 while unchanged files still re-ingest: first check `fileHash` fill
  (step 3) and gate fail-open warn logs (DEC-0119 §Decision-2 — an uncertain gate always
  proceeds), then the single-instance lock (was a second watcher running? runbook 0003).
- If the summary shows full-price re-ingest of everything after a startup: check for a DB wipe
  and the DEC-0120 row-count guard messages in startup logs.
