---
type: decision
id: DEC-0005
system: bensyne-mcp
title: "Namespace Parameter Enforcement"
status: accepted
createdAt: "2026-08-01T12:00:00Z"
updatedAt: "2026-08-16T00:00:00Z"
tags: [namespace, safety]
see_also: [decisions/0007-namespace-enforcement-breaking-change.decision.md, decisions/0002-namespace-parameter-enforcement.decision.md]
---

# DEC-0005: Namespace Parameter Enforcement

## Context
All memory tools silently default to "default" namespace when namespace parameter is omitted, causing accidental cross-namespace contamination.

## Decision
Make namespace parameter REQUIRED for all memory tools using `require_namespace()` validation helper.

## Rationale
1. **Safety** — Prevents accidental operations in wrong namespace
2. **Explicit intent** — Clients must consciously choose namespace
3. **Debugging** — Errors clearly indicate missing namespace
4. **Consistency** — Matches design philosophy of explicit over implicit

## Alternatives Considered
1. **Soft enforcement** — Warning log but still default — less safe
2. **Per-tool enforcement** — Inconsistent behavior
3. **No enforcement** — Current state — high risk

## Consequences
- **Positive**: Safer namespace handling
- **Negative**: Breaking change for existing clients
- **Mitigation**: Deprecation period with warnings, then hard enforcement (see DEC-0007)

## Status Note

> **2026-08-16:** Merged into shared DEC-0002 (`../../decisions/0002-namespace-parameter-enforcement.decision.md`) — the protocol-level decision; this node remains the bensyne-mcp system-specific record.
