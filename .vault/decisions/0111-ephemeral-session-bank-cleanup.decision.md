---
type: decision
id: DEC-0111
title: "Ephemeral Session Bank Cleanup via HTTP Endpoint"
status: accepted
createdAt: "2026-09-27T18:20:00Z"
updatedAt: "2026-09-27T18:20:00Z"
tags: [bensyne-mcp, session-management, cleanup, ttl]
system: bensyne-mcp
supersedes: []
superseded_by: []
see_also:
  - "decisions/0108-per-session-memory-banks.decision.md"
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