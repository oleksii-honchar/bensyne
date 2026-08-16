---
type: decision
id: DEC-0030
system: racochu
title: "Namespace Parameter Enforcement"
status: accepted
createdAt: "2026-08-01T12:00:00Z"
updatedAt: "2026-08-16T00:00:00Z"
tags: [namespace, mnemosyne, safety]
see_also: [concepts/0015-namespace-management.concept.md, decisions/0002-namespace-parameter-enforcement.decision.md]
---

# DEC-0030: Namespace Parameter Enforcement

## Context
All memory tools default to "default" namespace silently, creating cross-namespace contamination risk.

## Decision
Make namespace parameter required for all memory tools — no implicit fallback.

## Rationale
1. **Safety** — Prevents accidental cross-namespace operations
2. **Explicit intent** — Clients must consciously choose namespace
3. **Debugging** — Easier to trace which namespace was targeted
4. **Consistency** — Aligns with better-mnemosyne design philosophy

## Alternatives Considered
1. **Soft enforcement** — Warning but still default — less safe
2. **No enforcement** — Current state — high risk
3. **Per-tool enforcement** — Inconsistent behavior

## Consequences
- **Positive**: Safer namespace handling, explicit client behavior
- **Negative**: Breaking change for existing clients
- **Mitigation**: Deprecation period with warnings, then hard enforcement

## Status Note

> **2026-08-16:** Merged into shared DEC-0002 (`../../decisions/0002-namespace-parameter-enforcement.decision.md`) — the protocol-level decision; this node remains the racochu system-specific record.
