---
type: decision
id: DEC-0031
system: racochu
title: "In-Memory Namespace Registry"
status: accepted
createdAt: "2026-08-01T12:00:00Z"
updatedAt: "2026-08-16T00:00:00Z"
tags: [namespace, mnemosyne, infrastructure]
see_also: [decisions/0029-namespace-registration-on-startup.decision.md, concepts/0015-namespace-management.concept.md, decisions/0003-in-memory-namespace-registry.decision.md]
---

# DEC-0031: In-Memory Namespace Registry

## Context
Need to store namespace descriptions for the `register_namespace` tool.

## Decision
Use in-memory registry for namespace descriptions (no persistence).

## Rationale
1. **Simplicity** — No additional infrastructure
2. **Acceptable loss** — Descriptions are re-registered on RAG Content Chunker restart
3. **Low risk** — No data loss impact (descriptions are metadata)
4. **Fast access** — O(1) lookup

## Alternatives Considered
1. **File-based storage** — Persistent but adds complexity
2. **Database storage** — Overkill for simple key-value
3. **No storage** — Descriptions only available during registration

## Consequences
- **Positive**: Simple, fast, no persistence concerns
- **Negative**: Descriptions lost on server restart
- **Mitigation**: RAG Content Chunker re-registers on startup

## Status Note

> **2026-08-16:** Merged into shared DEC-0003 (`../../decisions/0003-in-memory-namespace-registry.decision.md`) — the protocol-level decision; this node remains the racochu system-specific record.
