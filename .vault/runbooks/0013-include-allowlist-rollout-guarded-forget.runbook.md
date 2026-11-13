---
type: runbook
system: racochu
title: "Rolling Out (or Narrowing) an Include Allow-List on a Live Source — Guarded Forgetting"
createdAt: "2026-11-13T16:33:29Z"
updatedAt: "2026-11-13T16:33:29Z"
tags: [racochu, operator, migration, reconciliation, mass-forget-guard]
see_also:
  - decisions/0122-watch-source-include-allowlist.decision.md
  - decisions/0125-reconciliation-out-of-scope-semantics.decision.md
  - runbooks/0003-troubleshooting.runbook.md
  - specifications/0011-watch-source-include-allowlist.spec.md
---

# Runbook: Include Allow-List Rollout with Guarded Forgetting

## Prerequisites
- Feature built (isPathInScope present in `dist/`) and the source's new include list
  decided; keep a backup of the current config.
- Optional pre-swap diff gate: walk the root with old vs new effective config; accept
  only when the dropped set is exactly the documented straggler families (counts drift;
  the DELTA is the invariant).

## Steps
1. Edit `~/.config/racochu.yaml` for the source: add `include:` (positive patterns),
   KEEP deliberately-residual directory excludes.
2. Restart the watcher (single-instance guard applies — stop the old process first).
3. Expect the FIRST reconciliation to REFUSE: log shows `outOfScopeMatched=<count>`
   above threshold 20; nothing is forgotten. Review the count against expectation.
4. Consent explicitly: restart once with `RACOCHU_RECONCILE_FORCE_FORGET=1`
   (standing rule: destructive operations only on explicit owner action).

## Verification
Reconciliation completes without refusal; out-of-scope memories gone; a sample
in-scope file still retrievable; second restart is quiet (no refusal expected).

## Rollback
Revert the config block; in-scope files re-ingest on demand via force-reprocess from
disk. Already-forgotten memories are not auto-restored by config rollback alone.

## Notes
The obsidian source's migration is BLOCKED until its configured path is confirmed on
the live machine (stale-path finding — operator-side).
