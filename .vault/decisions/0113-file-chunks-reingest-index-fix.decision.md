---
type: decision
id: DEC-0113
system: bensyne-mcp
title: "Fix file_chunks Index Management During Re-ingest"
status: accepted
createdAt: "2026-09-28T18:47:00Z"
updatedAt: "2026-09-28T18:47:00Z"
tags: [file-chunks, reingest, index, agent-persona, memory]
supersedes: []
superseded_by: []
see_also:
  - decisions/0109-episodic-memory-tier-migration.decision.md
  - decisions/0112-use-client-side-remember-episodic.decision.md
  - decisions/0114-verify-source-consistency-beam.decision.md
---

# DEC-0113: Fix file_chunks Index Management During Re-ingest

## Context

Agent-persona entries appeared to "disappear" from the decision tree over time. Investigation revealed that memories themselves remained in the `episodic_memory` table, but were reclassified as `occasional_memories` instead of `node_memories` by `getPersonaStatus`. The root cause: the `file_chunks` index records linking memories to their source files were being lost during re-ingest operations.

The `file_chunks` index is the authoritative link between memories and their source files. When this link is broken, the memory is still in the database but is no longer counted as a "node" — it becomes an "occasional memory" instead.

## Decision

Ensure the `delete_chunks_by_file_id()` method receives a correct exclude set during re-ingest operations. The exclude set must contain all live memory IDs for the file being re-ingested, so that the index records are not deleted when they should be preserved.

This is a defensive fix — ensure the index is maintained correctly during re-ingest rather than relying on post-hoc reconciliation.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|---|---|---|---|
| Rebuild entire index after re-ingest | Simple, guaranteed consistency | Expensive; requires scanning all episodic memories | Proactive fix is better than reactive rebuild |
| Add reconciliation job | Catches all index inconsistencies | Reactive; doesn't prevent the issue | Defensive approach prevents the loss in the first place |
| Do nothing (accept occasional loss) | Simple | Node counts drift over time | Not acceptable for production |
| Use database-level constraints | Robust | Complex; may not fit current schema | Defensive approach is simpler and effective |

## Consequences

- **Positive:** Node counts remain stable after re-ingest; agent-persona entries no longer "disappear"; `getPersonaStatus` accurately reflects file-backed vs occasional memories.
- **Negative:** Requires careful testing of the re-ingest path; adds complexity to the `delete_chunks_by_file_id()` call.
- **Neutral:** Does not change the episodic memory tier architecture established in ADR-13.

## Verification

- Integration tests: `test_reingest_chunk_index_integrity.py` (3 tests) — all passing
- Manual verification: re-ingested files retain their `file_chunks` index records
- `getPersonaStatus` node counts remain stable after re-ingest operations