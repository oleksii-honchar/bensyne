---
type: decision
id: DEC-0111
title: "Ephemeral Session Bank Cleanup via HTTP Endpoint"
status: accepted
createdAt: "2026-09-27T18:20:00Z"
updatedAt: "2026-10-08T20:33:16Z"
tags: [bensyne-mcp, session-management, cleanup, ttl]
system: bensyne-mcp
supersedes: []
superseded_by: []
see_also:
  - "decisions/0108-per-session-memory-banks.decision.md"
  - "decisions/0115-session-bank-regex-mixed-case.decision.md"
  - "decisions/0116-session-bank-age-durable-signal.decision.md"
  - "decisions/0117-cron-log-path-fail-loud.decision.md"
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# DEC-0111: Ephemeral Session Bank Cleanup via HTTP Endpoint

## Context

Bensyne MCP creates ephemeral memory banks for each agent session (`agent-session-ses_*`) that accumulate indefinitely. Empirical data showed 238 total banks with 156 ephemeral session banks (65%). An autoclean mechanism is needed to manage this growth and prevent unbounded disk usage.

## Decision

Implement a TTL-based cleanup mechanism for ephemeral session banks via a single HTTP endpoint:

- **HTTP endpoint:** `POST /api/v1/banks/cleanup` — for scheduled automated cleanup (called by external cron/scheduler)
- **Ephemeral bank identification:** Name prefix pattern matching (`^agent-session(-s)?_ses_[a-z0-9]+$`)
- **Retention policy:** TTL-based with 30-day default, configurable via endpoint parameters and environment variables
- **Safety defaults:** Dry-run mode is default; actual deletion requires explicit opt-in
- **Active client check:** Banks with active MnemosyneClient instances in the router pool are never deleted

The endpoint returns structured JSON with cleanup statistics (banks scanned, matched, eligible, deleted, skipped, errored).

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|---|---|---|---|
| HTTP endpoint only (selected) | Simple, safe, no agent surface | No MCP tool for ad-hoc cleanup | **Selected** — simpler and safer |
| HTTP + MCP tool | Automatic + manual | MCP tool dangerous for agents (could trigger cleanup mid-session) | Too risky |
| MCP tool only | Agent-accessible | Requires agent to remember; not automated | No automatic cleanup |
| Internal timer/scheduler | Fully automatic | Complex; introduces timer lifecycle management | Overkill |
| Session-end cleanup | Precise timing | Requires IPC complexity | Out of scope |
| Bank expiration metadata field | Explicit; future-proof | Requires schema migration; affects all bank operations | Too invasive |

## Consequences

- **Positive:** Prevents unbounded growth of ephemeral session banks on disk
- **Positive:** Simple, single code path with established safety mechanisms
- **Positive:** Follows existing `/health` custom_route pattern for admin endpoints
- **Positive:** Conservative 30-day default minimizes risk of premature deletion
- **Positive:** Dry-run default allows testing before enabling actual deletion
- **Negative:** No MCP tool for manual cleanup (HTTP endpoint can be called manually instead)
- **Negative:** New ephemeral bank naming patterns require code update to the pattern
- **Negative:** Disk usage continues to grow during the 30-day retention window
- **Neutral:** No change to MCP tool surface; relies on naming discipline already established in codebase

## Amendment (2026-10-08)

The mechanism was repaired without touching this decision's safety properties (HTTP-only surface, `dry_run=True` default, 30-day TTL, active-pool skip, dir-exists check):

- Identification regex corrected by [[0115-session-bank-regex-mixed-case]] — the pattern quoted above (`^agent-session(-s)?_ses_[a-z0-9]+$`) was found to match **0 real banks** (production IDs are mixed-case base62).
- Age signal replaced by [[0116-session-bank-age-durable-signal]] (creation marker + filesystem crtime; dir mtime proven unreliable).
- Cron wiring and observability hardened by [[0117-cron-log-path-fail-loud]].

This ADR remains the record of the original design choices (HTTP-only surface, no MCP tool, hard delete); it is **not superseded**.