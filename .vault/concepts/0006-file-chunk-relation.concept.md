---
type: concept
system: bensyne-mcp
title: "FileChunk and FileRelation Entities"
createdAt: "2026-08-12T00:00:00Z"
updatedAt: "2026-08-12T16:58:00Z"
tags: [domain, entity, file-chunk, file-relation, positional]
see_also:
  - decisions/0014-standalone-file-entities.decision.md
  - decisions/0017-file-content-reconstruction.decision.md
  - concepts/0004-file-metadata-aggregate.concept.md
---

# Concept: FileChunk and FileRelation Entities

## What

Two relationship entities that bridge files to memories and to each other:

**FileChunk** — the junction between a File and its Memory chunks:
- `id` — unique id (backfilled `file_id:memory_id`)
- `file_id` — reference to File
- `memory_id` — reference to Memory (in mnemosyne)
- `chunk_index` — position in chunk sequence (0-based, primary sort for reconstruction)
- `start_line` / `end_line` — line range in source file (secondary sort)
- `content_hash` — SHA-256 of chunk content for deduplication
- `content_type` — text, code, config, image, binary, unknown
- `is_partial` — flag for oversized chunks that were truncated

**FileRelation** — semantic relationships between files:
- `id` — unique id (backfilled `source:target:type`)
- `source_file_id` / `target_file_id` — the two files
- `relation_type` — 9 types: parent_child, sibling, backlink, folder_hierarchy, cross_reference, version, override, dependency, recommendation
- `strength` — float 0.0–1.0 (confidence in the relationship)
- `direction` — unidirectional or bidirectional
- `description` — optional human-readable explanation

## Why

FileChunk enables file content reconstruction from chunks (see DEC-0017) and tracks positional metadata lost in the memory store. FileRelation enables semantic file discovery (expandFileRelations tool) and supports Obsidian backlink patterns and agent session structure mapping.

## Key Details

- FileChunk is a frozen dataclass with Pydantic validation
- FileRelation is a frozen dataclass with Pydantic validation
- ORM: `FileChunkORM` composite PK `(file_id, memory_id)` + unique `id`; `FileRelationORM` composite PK `(source_file_id, target_file_id, relation_type)` + unique `id`
- `section_header` exists as a DB column but is NOT on the FileChunk entity
- Content is NOT stored in FileChunk — it exists in mnemosyne (the Memory)
- FileRelations are created by racochu during ingestion (source-specific)
