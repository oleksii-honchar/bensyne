---
type: adr
id: ADR-0013
title: "In-Memory Namespace Registry"
status: accepted
createdAt: "2026-08-01T12:00:00Z"
updatedAt: "2026-08-01T12:00:00Z"
tags: [namespace, mnemosyne, infrastructure]
see_also: ["adrs/0011-namespace-registration-on-startup.adr.md", "concepts/0008-namespace-management.concept.md"]
---

# ADR-0013: In-Memory Namespace Registry

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
