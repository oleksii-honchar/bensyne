---
type: decision
id: DEC-0001
system: shared
title: "Memory Bank Registration Protocol"
status: accepted
createdAt: "2026-08-16"
updatedAt: "2026-08-16"
tags: [memory-bank, mcp, protocol, registration]
see_also:
  - decisions/0004-namespace-registration-tool.decision.md
  - decisions/0029-namespace-registration-on-startup.decision.md
  - decisions/0003-in-memory-namespace-registry.decision.md
---

# DEC-0001: Memory Bank Registration Protocol

## Context

External systems that ingest content into the shared memory layer need a way to register memory-bank descriptions so agents can discover and understand what each memory bank contains. Historically this was framed as "namespace registration"; the current terminology is **memory bank**.

## Decision

The MCP protocol provides a **memory bank registration** mechanism: external systems **self-describe their storage** by registering (or updating) a memory-bank name plus description via the MCP server. Registration **happens at startup** of the external system — no manual configuration in the memory server is required or supported.

## Rationale

1. **Discoverability** — Agents can query memory-bank descriptions before operating
2. **Idempotency** — Safe to call multiple times (on every startup) with the same or an updated description
3. **External ownership** — Watch sources self-describe; no manual config in the memory server
4. **Bootstrap integration** — External systems register on startup, so descriptions are available proactively before agents query

## Alternatives Considered

1. **Hardcoded descriptions** — Fragile; requires memory-server code changes for each bank (bensyne perspective)
2. **Config file** — Manual management, out-of-sync risk (bensyne perspective)
3. **Lazy registration** — Register on first file chunk — less reliable (racochu perspective)
4. **Manual configuration** — Users register memory banks manually — error-prone (racochu perspective)
5. **No registration** — Agents discover banks only after memories exist / poor discoverability (both)

## Consequences

- **Positive**: Self-describing memory banks, agent discoverability, automatic registration
- **Negative**: Adds a registration tool to the MCP surface area; minor startup time impact
- **Mitigation**: Simple, well-tested implementation; async registration that does not block startup

## Per-System Implementation

### bensyne-mcp (server side)

- Exposes the MCP tool `registerMemoryBank(name, description)` (historically `register_namespace`) that allows external systems to register or update memory-bank descriptions.
- See `decisions/0004-namespace-registration-tool.decision.md` for the server-side ADR.

### racochu (client side)

- The RAG Content Chunker registers its memory banks with descriptions on application bootstrap (async, does not block startup).
- Multiple watchers can override a description — considered acceptable.
- See `decisions/0029-namespace-registration-on-startup.decision.md` for the client-side ADR.

## Status Note

> **2026-08-12:** Namespace terminology was superseded by memory-bank terminology. The tool is now `registerMemoryBank` (bensyne, see `src/app.py`). The decision principle — external systems self-describe their storage — remains in force.
>
> **2026-08-16:** Merged from bensyne-mcp DEC-0004 and racochu DEC-0029 into this protocol-level shared decision.
