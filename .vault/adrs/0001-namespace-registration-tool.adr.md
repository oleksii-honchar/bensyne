---
type: adr
id: ADR-0001
title: "Namespace Registration Tool"
status: accepted
createdAt: "2026-08-01T12:00:00Z"
updatedAt: "2026-08-01T12:00:00Z"
tags: [namespace, tool]
see_also: ["adrs/0003-in-memory-namespace-registry.adr.md"]
---

# ADR-0001: Namespace Registration Tool

## Context
External systems (RAG Content Chunker) need to register namespace descriptions so agents can discover and understand what each namespace contains.

## Decision
Add `register_namespace(name, description)` MCP tool that allows external systems to register or update namespace descriptions.

## Rationale
1. **Discoverability** — Agents can query namespace descriptions before operating
2. **Idempotency** — Safe to call multiple times with same or updated description
3. **External ownership** — Watch sources self-describe, no manual config in Mnemosyne
4. **Bootstrap integration** — RAG Content Chunker registers on startup

## Alternatives Considered
1. **Hardcoded descriptions** — Fragile, requires Mnemosyne code changes for each namespace
2. **Config file** — Manual management, out of sync risk
3. **No registration** — Agents discover namespaces only after memories exist

## Consequences
- **Positive**: Self-describing namespaces, agent discoverability
- **Negative**: Tool adds surface area to maintain
- **Mitigation**: Simple implementation, well-tested

## Status Note

> **2026-08-12:** Namespace terminology was superseded by memory-bank terminology. The tool described here is now `registerMemoryBank` (see `src/app.py`). The decision principle — external systems self-describe their storage — remains in force.
