---
type: decision
id: DEC-0116
title: "Session-Bank Age from Durable Metadata — Creation Marker + ext4 Birth Time"
status: accepted
createdAt: "2026-10-08T20:33:16Z"
updatedAt: "2026-10-08T20:33:16Z"
tags: [bensyne-mcp, session-management, cleanup, ttl, filesystem]
system: bensyne-mcp
supersedes: []
superseded_by: []
see_also:
  - "decisions/0111-ephemeral-session-bank-cleanup.decision.md"
  - "decisions/0108-per-session-memory-banks.decision.md"
  - "decisions/0115-session-bank-regex-mixed-case.decision.md"
  - "memories/0029-bank-dir-mtime-refreshed-by-server-activity.memory.md"
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# DEC-0116: Session-Bank Age from Durable Metadata — Creation Marker + ext4 Birth Time

## Context

Cleanup eligibility used bank-directory mtime vs a 30-day TTL. Dir mtime is reset by normal server activity (open/registration touches every bank; measured on puma 2026-10-08: all bank dirs mtime = same minute a `listMemoryBanks` ran; `mnemosyne.db` mtime also refreshed — see [[0029-bank-dir-mtime-refreshed-by-server-activity]]). Ephemeral banks are created implicitly via `router.get_bank_dir()` (DEC-0109, [[0108-per-session-memory-banks]]), so the bank registry has no `created_at` rows for them.

## Decision

Age resolution chain per bank, replacing mtime:
1. `.bank_created` marker file (single-line ISO-8601 UTC) written by `router.get_bank_dir()` **only in the new-directory branch** (`BANK_CREATED_MARKER` constant in router.py as single source of truth).
2. Fallback for pre-existing banks: ext4 birth time (crtime) via a ctypes `statx(2)` helper (`infrastructure/bank/birth_time.py`; Linux only; any failure → `None`).
3. Neither available → `age_source="unknown"`: bank is **never deleted**, counted in report field `banks_skipped_unknown_age`. Every candidate carries `age_source: marker|birth_time|unknown`.

This does **not** contradict [[0111-ephemeral-session-bank-cleanup]]'s rejection of a "bank expiration metadata field": no schema change, no domain metadata — filesystem marker + filesystem crtime, invisible to bank operations.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|---|---|---|---|
| Registry `created_at` | Already exists, queryable | No rows for implicitly-created ephemeral banks (verified) | Doesn't cover the 478 banks |
| `mnemosyne.db` file mtime | No code at creation | Measured refreshed by server activity — same failure class | Empirically dead |
| Timestamp embedded in session ID | No storage at all | Codec undocumented | Unverifiable assumption |
| One-off backfill script | Uniform signal after deploy | No trustworthy source to backfill from (all mtimes already refreshed) | crtime covers existing banks for free |
| Skip unknown-age only (no fallback) | Simplest safe rule | Legacy banks never cleaned on puma (crtime available there) | Defeats the purpose |

## Consequences

- **Positive:** Correct ages for new AND existing banks without migration.
- **Positive:** Unknown-age is fail-safe — no deletion on a guess; visible in the report.
- **Negative:** ~30 lines of statx ctypes helper; one extra file per new bank dir (inert to all readers).
- **Neutral:** With correct ages, the first eligible cohort appears ~2026-10-22 (banks born 2026-09-22 under 30-day TTL) — expected policy behavior, not a regression.
