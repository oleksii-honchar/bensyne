---
type: concept
title: "Namespace Routing"
createdAt: "2026-07-31T07:30:00Z"
updatedAt: "2026-08-01T21:35:00Z"
tags: [mnemosyne, infrastructure, namespace]
see_also: ["adrs/0008-remote-database-segregation.adr.md", "concepts/0003-enhancement-pipeline.concept.md", "concepts/0008-namespace-management.concept.md"]
---

# Concept: Namespace Routing

## What

Namespace routing is the mechanism by which the remote Mnemosyne server (better-mnemosyne) segregates memories from different sources into separate SQLite databases using the `namespace` parameter.

## Why

Mnemosyne's SQLite backend has scalability limits (~500K memories per database). Separating sources into dedicated databases prevents one large source from affecting others and enables per-source monitoring and maintenance.

## Key Details

**Configured per watch source:**
```yaml
watchSources:
  - id: agent-sessions
    path: ~/.agent-sessions
    namespace: agent-sessions  # → server routes to agent-sessions/mnemosyne.db
    description: "Agent session files — research, specs, decisions"
  - id: obsidian-vault
    path: ~/obsidian
    namespace: obsidian  # → server routes to obsidian/mnemosyne.db
    description: "Obsidian vault notes — personal knowledge base"
```

**Flow:**
1. Watch source defines namespace (defaults to source id if omitted)
2. EnhancementPipelineService assigns namespace to each Chunk
3. MnemosyneClient sends `namespace` in `mnemosyne_remember` call
4. Remote better-mnemosyne server routes to `{namespace}/mnemosyne.db`
5. Creates database if it doesn't exist

**Client perspective:** RAG Content Chunker only sends namespace — all database routing is server-side. Client never sees file paths or DB internals.

**Multiple sources can share namespace:** Two watch sources pointing to different directories can use the same namespace → same database.

## Namespace Registration

RAG Content Chunker registers namespace descriptions on startup via `register_namespace(name, description)` MCP tool. This enables agents to discover namespaces and understand their purpose before operating on them. Registration is idempotent — safe on every restart.

## Namespace Enforcement

The `namespace` parameter is now **required** for all memory tools (remember, recall, forget, update, sleep). Missing namespace triggers `ValidationError: namespace parameter is required`. No implicit fallback to "default" namespace.

## Discovery

Agents can query `list_namespaces` to get:
- `name` — namespace name
- `description` — human-readable description (from NamespaceRegistry)
- `memory_count` — approximate memory count
- Default namespace has hardcoded description: "Default personal memory — general conversation context, preferences, and facts"
