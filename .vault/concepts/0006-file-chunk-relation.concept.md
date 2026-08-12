---
type: concept
title: "FileChunk and FileRelation Entities"
createdAt: "2026-08-12T00:00:00Z"
updatedAt: "2026-08-12T00:00:00Z"
tags: [domain, entity, file-chunk, file-relation, positional]
see_also:
  - "adrs/0011-standalone-file-entities.adr.md"
  - "adrs/0014-file-content-reconstruction.adr.md"
  - "concepts/0004-file-metadata-aggregate.concept.md"
---

# Concept: FileChunk and FileRelation Entities

## What

Two relationship entities that bridge files to memories and to each other:

**FileChunk** — the junction between a File and its Memory chunks:
- `file_id` — reference to File
- `memory_id` — reference to Memory (in mnemosyne)
- `chunk_index` — position in chunk sequence (0-based, primary sort for reconstruction)
- `start_line` / `end_line` — line range in source file (secondary sort)
- `content_hash` — SHA-256 of chunk content for deduplication
- `content_type` — TEXT, CODE, CONFIG, IMAGE, BINARY, UNKNOWN
- `is_partial` — flag for oversized chunks that were truncated

**FileRelation** — semantic relationships between files:
- `source_file_id` / `target_file_id` — the two files
- `relation_type` — 9 types: PARENT_CHILD, SIBLING, BACKLINK, FOLDER_HIERARCHY, CROSS_REFERENCE, VERSION, OVERRIDE, DEPENDENCY, RECOMMENDATION
- `strength` — float 0.0–1.0 (confidence in the relationship)
- `direction` — UNIDIRECTIONAL or BIDIRECTIONAL
- `description` — optional human-readable explanation

## Why

FileChunk enables file content reconstruction from chunks (see ADR-0014) and tracks positional metadata lost in the memory store. FileRelation enables semantic file discovery (expandFileRelations tool) and supports Obsidian backlink patterns and agent session structure mapping.

## Key Details

- FileChunk is a frozen dataclass with Pydantic validation
- FileRelation is a frozen dataclass with Pydantic validation
- FileChunk's `(file_id, memory_id)` is the composite primary key in SQLite
- FileRelation's `(source_file_id, target_file_id, relation_type)` is the composite primary key
- Content is NOT stored in FileChunk — it exists in mnemosyne (the Memory)
- FileRelations are created by racochu during ingestion (source-specific)
