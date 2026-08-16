---
type: adr
id: ADR-0003
title: "In-Memory Namespace Registry"
status: accepted
createdAt: "2026-08-01T12:00:00Z"
updatedAt: "2026-08-01T12:00:00Z"
tags: [namespace, infrastructure]
see_also: ["adrs/0001-namespace-registration-tool.adr.md"]
---

# ADR-0003: In-Memory Namespace Registry

## Context
Need to store namespace descriptions for the `register_namespace` tool and expose them in `list_namespaces`.

## Decision
Use in-memory `NamespaceRegistry` class with `Dict[str, str]` for namespace → description mapping.

## Rationale
1. **Simplicity** — No additional infrastructure (no DB, no file I/O)
2. **Acceptable loss** — Descriptions re-registered by RAG Content Chunker on every startup
3. **Low risk** — Descriptions are metadata only, no operational impact if lost
4. **Fast** — O(1) lookup

## Alternatives Considered
1. **SQLite persistence** — Overkill for volatile metadata
2. **JSON file** — Adds I/O complexity, file locking issues
3. **Env vars** — Fragile, hard to update

## Consequences
- **Positive**: Simple, fast, no persistence concerns
- **Negative**: Descriptions lost on Mnemosyne server restart
- **Mitigation**: RAG Content Chunker re-registers all namespaces on bootstrap

## Status Note

> **2026-08-12:** `NamespaceRegistry` was renamed to `MemoryBankRegistry` (`src/infrastructure/bank/registry.py`) during the memory-bank terminology migration. Still an in-memory dict, still re-registered on startup.
