---
type: concept
system: bensyne-mcp
title: "FileMetadata"
createdAt: "2026-08-12T00:00:00Z"
updatedAt: "2026-08-18T07:55:43Z"
tags: [domain, aggregate, file-metadata, rich-domain]
see_also:
  - decisions/0014-standalone-file-entities.decision.md
  - decisions/0033-aggregate-repository-service-pattern.decision.md
  - concepts/0006-file-chunk-relation.concept.md
  - concepts/0023-materialization.concept.md
  - architectures/bensyne-mcp/code/0001-file-metadata.code.md
---

# Concept: FileMetadata

## What

The `FileMetadata` class (renamed from `FileMetadataAggregate`, 2026-08-18) is the aggregate root for file metadata operations. It enforces invariants across the File, FileChunk, and FileRelation entities and produces domain events via `Result.events`, and is the **sole write root** for File/FileChunk/FileRelation rows: every write is load aggregate → domain mutation (invariants + events) → one private `_persist` chokepoint in `FileService` (D17).

*File-name note:* the class lives in `file_metadata_aggregate.py` — the `_aggregate` suffix is a codebase pattern marker (cf. `MemoryBank` in `memory_bank_aggregate.py`), not a class-name remnant.

## Why

Without an aggregate, file-chunk relationships would be managed by the application layer, violating the rich domain model principle. The aggregate centralizes:
- Chunk uniqueness enforcement (no duplicate memory_id per file)
- Content composition (aggregate knows how to compose content from chunks)
- Metadata aggregation (keywords/tags merged on chunk add/remove via File.with_chunk()/without_chunk())
- Domain event production (one event class per fact: `FileChunkCreatedEvent`, `FileChunkUpdatedEvent`, `FileChunkRemovedEvent`, etc.)

## Key Details

- **Frozen dataclass** — immutable; updates produce new instances
- **Composition methods:**
  - `compose_content(mnemosyne_client: Callable, summary_only=False)` — composes file content from chunks, emits `FileContentComposedEvent`
  - `to_dict(include_relation_type, include_content, summary_only, mnemosyne_client)` — serializes aggregate for MCP output
- **Chunk operations:**
  - `upsert_chunk(chunk)` — idempotent: no chunk for `memory_id` → add; different `chunk_index` → replace; differing updatable fields → update in place; all equal → **silent no-op** (zero events, zero rows). Emits exactly one `FileChunkCreatedEvent` / `FileChunkUpdatedEvent` per change; delegates metadata merge to File.with_chunk()/without_chunk()
  - `remove_chunk(memory_id)` — emits `FileChunkRemovedEvent`, delegates to File.without_chunk()
- **Relation operations:**
  - `upsert_relation(relation)` — idempotent: dedup key `(target_file_id, relation_type)` scoped to the aggregate's file as source; canonical id `fr_{source}_{target}_{type}`; differing strength/description/direction → in-place update; equal → silent no-op
- **Content composition lives in the aggregate** — use case delegates to aggregate, not builds dict itself
