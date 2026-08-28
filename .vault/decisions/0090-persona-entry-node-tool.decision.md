---
type: decision
id: DEC-0091
system: bensyne-mcp
title: "Dedicated getPersonaEntryNode MCP Tool"
status: accepted
createdAt: "2026-08-28T10:58:47Z"
updatedAt: "2026-08-28T10:58:47Z"
tags: [bensyne-mcp, persona, traversal, mcp-tool, recall]
supersedes: []
superseded_by: []
see_also:
  - decisions/0091-file-tools-file-id-contract.decision.md
  - decisions/0089-persona-tree-walk-tilde-expansion.decision.md
  - runbooks/0007-persona-tree-traversal-diagnosis.runbook.md
---

# DEC-0091: Dedicated getPersonaEntryNode MCP Tool

## Context

The documented entry-node lookup (`recallMemory(query: "entry node")`) failed: the FTS
index (`fts_working`) covers `content` only — `persona.entry`, `persona.node_id`,
`persona.title`, and tags are not indexed, and no node body contains the words
"entry node". Agents fell back to reading node files from disk instead of traversing
memory. A direct library test confirmed: `recall('entry node')` = 0 results,
`recall('start read session')` = 1 (the entry node).

## Decision

Add a dedicated MCP tool `getPersonaEntryNode(memory_bank)` that returns the node with
`persona.entry: "true"` directly — no semantic search.

- Response contract (6 keys): `{memory_id, file_id, title, text, metadata, tags}`.
- `file_id` is the id for `expandFileRelations` (per DEC-0092).
- No entry node → `Result.ko` `ENTRY_NODE_NOT_FOUND`; missing/empty bank →
  `MEMORY_BANK_REQUIRED`.
- **Final implementation:** the use case reads the entry flag from
  `file_metadata.db` (`files.metadata`) via `FileRepository.list_files()` plus the
  chunk→memory content link. An earlier variant read BEAM `working_memory`/
  `episodic_memory` `metadata_json` and failed e2e (empty `{}` metadata in
  `mnemosyne.db` for persona nodes); it was replaced during Task 6 verification (TDD
  RED 0 → GREEN 17/17) and the dead client method removed.
- Skills protocol: prefer `getPersonaEntryNode`; fall back to `recallMemory` with
  **content-bearing terms from the entry node body** — never the literal
  `"entry node"` query.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| Index metadata in FTS (persona.entry, node_id, tags) | Keeps recall as the only lookup path | Migration + re-index of all banks; still tokenizer-fragile | Higher effort, still fragile |
| Content-bearing recall queries only | No server change | Depends on query terms matching node bodies | Kept as fallback, not primary |

## Consequences

- **Positive:** deterministic entry-node discovery; the STOP-and-flag rule (tree present or not) is now enforceable with one tool call. Live-verified 2026-08-28: 11/11 persona banks return a valid entry node.
- **Negative:** new MCP tool surface (schema, handler, use case, DI factory, 25+ tests).

*Verified 2026-08-28: tool registered in `apps/bensyne-mcp/src/app.py`; handler in `src/infrastructure/mcp/handlers.py`; DI in `src/infrastructure/di.py`; use case uses `FileRepository.list_files()`.*
