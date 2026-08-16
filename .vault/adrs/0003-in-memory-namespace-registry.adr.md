---
type: adr
id: ADR-SYS-0003
title: "In-Memory Memory Bank Registry"
status: accepted
createdAt: "2026-08-16"
updatedAt: "2026-08-16"
tags: [memory-bank, mcp, protocol, infrastructure]
see_also:
  - "systems/bensyne-mcp/adrs/0003-in-memory-namespace-registry.adr.md"
  - "systems/racochu/adrs/0013-in-memory-namespace-registry.adr.md"
  - "adrs/0001-namespace-registration-protocol.adr.md"
---

# ADR-SYS-0003: In-Memory Memory Bank Registry

## Context

The memory server needs to store memory-bank descriptions registered via the MCP registration protocol (historically "namespace descriptions") and expose them for listing/discovery.

## Decision

Store memory-bank descriptions in an **in-memory registry** — a `Dict[str, str]` mapping memory-bank name → description — with **no persistence**. Because registrations are re-sent by external systems at startup, loss on server restart is acceptable.

## Rationale

1. **Simplicity** — No additional infrastructure (no DB, no file I/O)
2. **Acceptable loss** — Descriptions are re-registered by external systems (e.g. RAG Content Chunker) on every startup
3. **Low risk** — Descriptions are metadata only; no operational impact if lost
4. **Fast** — O(1) lookup

## Alternatives Considered

1. **SQLite / database persistence** — Overkill for volatile metadata (bensyne: "overkill"; racochu: "overkill for simple key-value")
2. **JSON / file storage** — Adds I/O complexity, file-locking issues; persistent but more complexity than needed
3. **Env vars** — Fragile, hard to update
4. **No storage** — Descriptions only available during registration (racochu perspective)

## Consequences

- **Positive**: Simple, fast, no persistence concerns
- **Negative**: Descriptions lost on memory server restart
- **Mitigation**: External systems re-register all memory banks on bootstrap

## Per-System Implementation

### bensyne-mcp (server side)

- `MemoryBankRegistry` (historically `NamespaceRegistry`) in `src/infrastructure/bank/registry.py` — in-memory `Dict[str, str]`, re-populated on startup via `registerMemoryBank`.

### racochu (client side)

- The RAG Content Chunker treats registry descriptions as volatile: it re-registers its memory banks on every application startup, so server-side in-memory storage is sufficient.
- See `systems/racochu/adrs/0013-in-memory-namespace-registry.adr.md` for the client-side ADR.

## Status Note

> **2026-08-12:** `NamespaceRegistry` was renamed to `MemoryBankRegistry` (`src/infrastructure/bank/registry.py`) during the memory-bank terminology migration. Still an in-memory dict, still re-registered on startup.
>
> **2026-08-16:** Merged from bensyne-mcp ADR-0003 and racochu ADR-0013 into this protocol-level shared ADR.
