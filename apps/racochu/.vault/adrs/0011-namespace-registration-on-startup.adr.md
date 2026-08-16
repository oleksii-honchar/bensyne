---
type: adr
id: ADR-0011
title: "Namespace Registration on Startup"
status: accepted
createdAt: "2026-08-01T12:00:00Z"
updatedAt: "2026-08-01T12:00:00Z"
tags: [namespace, mnemosyne]
see_also: ["concepts/0008-namespace-management.concept.md", "concepts/0004-namespace-routing.concept.md"]
---

# ADR-0011: Namespace Registration on Startup

## Context
Agents cannot discover or understand namespaces because watch sources never register descriptions.

## Decision
RAG Content Chunker registers namespaces with descriptions on application bootstrap.

## Rationale
1. **Discoverability** — Agents can understand what namespaces contain
2. **Idempotency** — Safe to run on every startup
3. **User Awareness** — Multiple watchers can override (acceptable)
4. **Proactive** — Descriptions available before agents query

## Alternatives Considered
1. **Lazy registration** — Register on first file chunk — less reliable
2. **Manual configuration** — Users register namespaces manually — error-prone
3. **No registration** — Current state — poor discoverability

## Consequences
- **Positive**: Better namespace discoverability, automatic registration
- **Negative**: Startup time impact (minimal)
- **Mitigation**: Async registration, don't block startup
