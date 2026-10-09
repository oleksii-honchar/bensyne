---
type: runbook
system: bensyne-mcp
title: "Session-Bank Cleanup — Deploy & Verify on puma.lan"
createdAt: "2026-10-08T20:33:16Z"
updatedAt: "2026-10-08T20:33:16Z"
tags: [cleanup, cron, puma-lan, operations, session-banks]
see_also:
  - "decisions/0111-ephemeral-session-bank-cleanup.decision.md"
  - "decisions/0115-session-bank-regex-mixed-case.decision.md"
  - "decisions/0116-session-bank-age-durable-signal.decision.md"
  - "decisions/0117-cron-log-path-fail-loud.decision.md"
---

# Runbook: Session-Bank Cleanup — Deploy & Verify on puma.lan

## Prerequisites

- Updated bensyne-mcp image (C1–C2b) and updated `puma-lan/lite-llm/mcp/bensyne/` cron scripts (C3–C4).
- SSH access to puma.lan as `tuiteraz`; container `bensyne-mcp` on port 3010.

## Steps

1. Redeploy the `bensyne-mcp` container (port 3010 unchanged).
2. `cd ~/puma-lan/lite-llm/mcp/bensyne && ./setup-cron.sh install` (idempotent; replaces the broken `/var/log` entry).
3. Reviewed dry-run: `curl -s -X POST -H 'Content-Type: application/json' -d '{"dry_run": true}' http://localhost:3010/api/v1/banks/cleanup`
4. Review the candidate list before letting cron `execute` (installed mode is already `execute`).
5. One-off junk cleanup (operator, manual): `find data/banks -maxdepth 1 -name '._*' -delete`; remove `.DS_Store`; decide manually on `session-ses_*` / bare `ses_*` / `.trash-*` banks (outside the cleanup pattern by policy).

## Verification

- Dry-run reports `banks_matched > 0` (≈478) with `age_source` populated for every candidate.
- `banks_skipped_unknown_age` visible; unknown-age banks never deleted.
- Cron log appears at `lite-llm/mcp/bensyne/logs/bensyne-cleanup.log`; job exits non-zero if it matches 0 banks while banks exist.
- First real deletions expected only from ~2026-10-22 (oldest cohort born 2026-09-22, 30-day TTL) — zero eligible before that is correct behavior, not a regression.

## Rollback

Cleanup is gated by `dry_run=True` default + TTL + pool-skip; to stop deletions, remove the crontab entry via `./setup-cron.sh remove`. Deletions are hard (`shutil.rmtree`) — no undo; rely on the dry-run review step.
