---
type: decision
id: DEC-0002
system: shared
title: "Memory Bank Parameter Enforcement"
status: accepted
createdAt: "2026-08-16"
updatedAt: "2026-08-16"
tags: [memory-bank, mcp, protocol, safety]
see_also:
  - decisions/0005-namespace-parameter-enforcement.decision.md
  - decisions/0030-namespace-parameter-enforcement.decision.md
  - decisions/0001-namespace-registration-protocol.decision.md
---

# DEC-0002: Memory Bank Parameter Enforcement

## Context

All memory tools silently default to the "default" memory bank when the memory-bank parameter is omitted (historically the "namespace" parameter), causing accidental cross-bank contamination.

## Decision

Make the memory-bank parameter **REQUIRED** for all memory operations exposed over the MCP protocol — no implicit fallback to a default bank. Clients must explicitly name the memory bank for every operation.

## Rationale

1. **Safety** — Prevents accidental operations in the wrong memory bank (cross-bank contamination)
2. **Explicit intent** — Clients must consciously choose the memory bank
3. **Debugging** — Missing-bank errors clearly indicate the problem; easier to trace which bank was targeted
4. **Consistency** — Matches the design philosophy of explicit over implicit

## Alternatives Considered

1. **Soft enforcement** — Warning log but still default — less safe (both systems)
2. **Per-tool enforcement** — Inconsistent behavior (bensyne, racochu)
3. **No enforcement** — Prior state — high risk (both systems)

## Consequences

- **Positive**: Safer memory-bank handling, explicit client behavior
- **Negative**: Breaking change for existing clients
- **Mitigation**: Deprecation period with warnings, then hard enforcement

## Per-System Implementation

### bensyne-mcp (server side)

- Enforced via the `require_namespace()` validation helper (renamed with the memory-bank terminology migration) applied to all memory tools.
- The breaking-change rollout strategy lives in `decisions/0007-namespace-enforcement-breaking-change.decision.md`.

### racochu (client side)

- The RAG Content Chunker passes the memory bank explicitly on every operation — no reliance on implicit defaults; aligns with the better-mnemosyne design philosophy.
- See `decisions/0030-namespace-parameter-enforcement.decision.md` for the client-side ADR.

## Status Note

> **2026-08-12:** Namespace terminology was superseded by memory-bank terminology. The enforced parameter is the memory bank; the validation helper is named after the historical "namespace" concept.
>
> **2026-08-16:** Merged from bensyne-mcp DEC-0005 and racochu DEC-0030 into this protocol-level shared decision.
