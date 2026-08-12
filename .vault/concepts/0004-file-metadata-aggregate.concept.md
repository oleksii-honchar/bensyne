---
type: concept
title: "FileMetadataAggregate"
createdAt: "2026-08-12T00:00:00Z"
updatedAt: "2026-08-12T00:00:00Z"
tags: [domain, aggregate, file-metadata, rich-domain]
see_also:
  - "adrs/0011-standalone-file-entities.adr.md"
  - "concepts/0006-file-chunk-relation.concept.md"
  - "architectures/bensyne/0002-file-metadata.code.md"
---

# Concept: FileMetadataAggregate

## What

The `FileMetadataAggregate` is the aggregate root for file metadata operations. It enforces invariants across the File, FileChunk, and FileRelation entities and produces domain events via `Result.events`.

## Why

Without an aggregate, file-chunk relationships would be managed by the application layer, violating the rich domain model principle. The aggregate centralizes:
- Chunk uniqueness enforcement (no duplicate memory_id per file)
- Content composition (aggregate knows how to compose content from chunks)
- Metadata aggregation (keywords/tags merged on chunk add/remove via File.with_chunk()/without_chunk())
- Domain event production (FileChunkAddedEvent, FileChunkRemovedEvent, etc.)

## Key Details

- **Frozen dataclass** — immutable; updates produce new instances
- **Composition methods:**
  - `compose_content(mnemosyne_client: Callable, summary_only=False)` — composes file content from chunks, emits `FileContentComposedEvent`
  - `to_dict(include_relation_type, include_content, summary_only, mnemosyne_client)` — serializes aggregate for MCP output
- **Chunk operations:**
  - `add_chunk(chunk)` — enforces uniqueness, emits `FileChunkAddedEvent`, delegates to File.with_chunk()
  - `remove_chunk(memory_id)` — emits `FileChunkRemovedEvent`, delegates to File.without_chunk()
- **Relation operations:**
  - `add_relation(relation)` — emits `FileRelationCreatedEvent`
- **Content composition lives in the aggregate** — use case delegates to aggregate, not builds dict itself
