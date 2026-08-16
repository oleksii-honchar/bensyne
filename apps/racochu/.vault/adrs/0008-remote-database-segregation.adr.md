---
type: adr
id: ADR-0008
title: "Remote Database Segregation"
status: accepted
createdAt: "2026-07-30T23:00:00Z"
updatedAt: "2026-07-31T07:30:00Z"
tags: [infrastructure, mnemosyne, scalability]
see_also: ["concepts/0004-namespace-routing.concept.md"]
---

# ADR-0008: Remote Database Segregation

## Context

Mnemosyne uses SQLite with single-writer limitations. Remote MCP server needs to handle multiple watch sources without performance degradation.

## Decision

Remote Mnemosyne server (better-mnemosyne) implements per-namespace database segregation. Client (RAG Content Chunker) only sends `namespace` parameter in `mnemosyne_remember` calls; server routes to separate SQLite databases per namespace.

Watch source config defines namespace (defaults to source id):
```yaml
watchSources:
  - id: agent-sessions
    path: ~/.agent-sessions
    namespace: agent-sessions  # → server routes to agent-sessions/mnemosyne.db
```

## Alternatives Considered

1. **Single shared database** — All sources use one database
2. **PostgreSQL migration** — Migrate entire system to PostgreSQL
3. **Memory banks** — Use Mnemosyne's existing bank feature

## Consequences

- **Positive**: Better performance, easier management, source isolation
- **Negative**: Server-side complexity, multiple files to maintain
- **Mitigation**: Server handles routing transparently; client just sets namespace

## Scalability Note

Mnemosyne SQLite supports up to ~500K memories per database. Migration path to PostgreSQL hybrid for >500K documented in session materials but not implemented.
