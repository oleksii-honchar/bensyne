---
type: decision
id: DEC-0108
system: bensyne-mcp
title: "ADR-11: Content-sync fix for hash deduplication"
status: accepted
createdAt: "2026-09-07T13:05:59Z"
updatedAt: "2026-09-07T13:05:59Z"
tags: [deduplication, content-sync, mcp-tool, bensyne-mcp]
supersedes: []
superseded_by: []
see_also:
  - decisions/0086-recover-force-reembed.decision.md
  - decisions/0090-persona-entry-node-tool.decision.md
  - concepts/0020-file-hash-deduplication.concept.md
---

# ADR-11: Content-sync fix for hash deduplication

## Problem

The `RememberMemoryUseCase` uses chunk hash deduplication to avoid duplicate embeddings. When a file is re-ingested with the same chunk hash, the use case returns the existing `memory_id` without updating the content. However, the memory's `content` field can be empty or stale (e.g., due to external loss, `sleep()` consolidation, or other bugs), causing `getPersonaEntryNode` to return empty text even though the file on disk has content.

## Decision

On every dedup hit, call `mnemosyne.update()` to sync the memory's content from the new input. This ensures the memory's `content` field is always in sync with the ingested content, regardless of whether the previous content was empty, stale, or different.

## Implementation

Modified `apps/bensyne-mcp/src/application/use_cases/remember_memory_use_case.py`:

- On dedup hit, before returning the existing memory_id, call `self.memory_repository.update(existing_memory_id, content=parameters.get("content", ""))`.
- Log a warning if the update fails, but continue with the dedup response.

## Rationale

- The memory's `content` field is a cache that must stay in sync with the FileChunk.
- The hash index prevents duplicate embeddings, but the content still needs updating.
- This is a targeted fix that addresses the root cause without changing the dedup logic itself.
- The `force_reembed` mechanism (ADR-8) handles the case where the memory no longer exists at all; this fix handles the case where it exists but has empty/stale content.

## Tests

Added integration tests in `apps/bensyne-mcp/src/tests/integration/test_dedup_content_refresh.py`:

- `test_reingest_refreshes_empty_content`: Verifies that when a memory has empty content, re-ingestion refreshes it.
- `test_reingest_with_updated_content_refreshes`: Verifies that when a file is re-ingested with updated content, the memory is updated.
- `test_nonempty_memory_not_redundantly_updated`: Verifies that when the memory already has the correct content, no redundant update is performed.

## Related

- ADR-8: Stale dedup hit repair (`force_reembed` mechanism)
- Bug: Empty text in `getPersonaEntryNode` for icm-operator persona bank

## Notes

The filesystem fallback previously added to `GetPersonaEntryNodeUseCase` was removed as part of this fix. The Bensyne MCP server does not have filesystem access to the `agent-personas` directory — the content-sync fix in `RememberMemoryUseCase` is the correct solution.