---
type: specification
kind: refactor
status: active
title: "Session-Bank Cleanup Repair (C1–C4)"
owner: ""
createdAt: "2026-10-08T20:33:16Z"
updatedAt: "2026-10-08T20:33:16Z"
system: bensyne-mcp
tags: [cleanup, ttl, cron, session-banks, puma-lan]
see_also:
  - "decisions/0111-ephemeral-session-bank-cleanup.decision.md"
  - "decisions/0115-session-bank-regex-mixed-case.decision.md"
  - "decisions/0116-session-bank-age-durable-signal.decision.md"
  - "decisions/0117-cron-log-path-fail-loud.decision.md"
  - "runbooks/0010-session-bank-cleanup-verification.runbook.md"
---

# Specification: Session-Bank Cleanup Repair (C1–C4)

## Goal

Make the ephemeral session-bank cleanup ([[0111-ephemeral-session-bank-cleanup]]) actually work on puma.lan: identify real banks, derive age from a durable signal, run the cron with a writable log, and fail loudly on silent no-ops — while preserving every intentional safety property of DEC-0111 (HTTP-only surface, `dry_run=True` default, 30-day TTL, active-pool skip, dir-exists check).

## Problem (diagnosed 2026-10-08)

Three stacked failures, each alone sufficient to make cleanup a no-op: (1) crontab log redirect to unwritable `/var/log` — script never ran; (2) regex matched 0 of 478 real banks; (3) dir-mtime TTL reset by normal server activity.

## Changes (all implemented, reviewer PASS 2026-10-08)

- **C1** — regex widened to `^agent-sessions?[-_]ses_[A-Za-z0-9]+$` (DEC-0115); test assumption inverted.
- **C2a** — `.bank_created` marker written by `router.get_bank_dir()` only on new-directory creation.
- **C2b** — age chain marker → `statx` birth time → unknown (never deleted, `banks_skipped_unknown_age`); every candidate carries `age_source` (DEC-0116). New helper `infrastructure/bank/birth_time.py`.
- **C3+C4** — cron log to `${SCRIPT_DIR}/logs/`, fail-loud exit 2 on matched-0-while-scanned>0 (DEC-0117).

## Interfaces

HTTP surface unchanged (`POST /api/v1/banks/cleanup`); report fields additive only. Filesystem addition: `{banks_root}/{bank}/.bank_created` (single-line ISO-8601 UTC, written once, ignored by all readers).

## Non-goals

No MCP cleanup tool (DEC-0111 rejected it). No bank naming, registry schema, or migration changes. No trash-then-purge (hard delete kept, per DEC-0111). One-off junk (`._*`, `.DS_Store`, `session-ses_*`, bare `ses_*`, `.trash-*`) is operator cleanup, not code.

## Status / Acceptance

Code-complete and green (1259 passed; 1 known pre-existing baseline red tracked separately; 1 Linux-only skip). Remaining acceptance is operator deployment — see runbook [[0010-session-bank-cleanup-verification]]. First real deletions expected ~2026-10-22 under the 30-day TTL.
