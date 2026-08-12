---
type: concept
title: "Source Type Taxonomy and File Type Classification"
createdAt: "2026-08-12T00:00:00Z"
updatedAt: "2026-08-12T16:58:00Z"
tags: [domain, taxonomy, source-type, file-role, racochu]
see_also:
  - "adrs/0013-racochu-source-enrichment.adr.md"
  - "concepts/0007-file-metadata-layer.concept.md"
---

# Concept: Source Type Taxonomy and File Type Classification

## What

Two orthogonal taxonomies classify files in the bensyne system:

**Source Type** — where the file came from (enum `SourceType` in `src/domain/models/file_model.py`):
- `agent_session` — files from agent sessions (session.md, artifacts, etc.)
- `file_system` — files from local file system ingestion
- `git` — files from git repos
- `database` — files originating from databases
- `external` — external sources
- `remote` — remote sources
- `unknown` — unclassified (racochu default when sourceId is missing)

**File Type** — what kind of file it is (optional `file_type` string field, aligned with racochu):
- `config` — configuration files (package.json, tsconfig.json, .env, etc.)
- `code` — source code files (.ts, .js, .py, .rs, etc.)
- `docs` — documentation files (.md, .txt, .rst, etc.)

## Why

Source type determines how racochu processes and enriches the file (chunking strategy, relation composition). File type determines how bensyne treats the file for search purposes. The separation allows bensyne to accept unified metadata from any source while racochu handles source-specific logic.

## Key Details

- Source type is a required field on File entities
- File type is optional (defaults based on file extension in racochu)
- Source type drives racochu's enrichment pipeline (see ADR-0013)
- File type is used in search filtering (searchFiles tool `file_role` parameter)
- Additional source types can be added without modifying bensyne (racochu maps `sourceId` → SourceType via `SOURCE_TYPE_MAP`)
