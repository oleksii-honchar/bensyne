---
type: concept
title: "Source Type Taxonomy and File Role Classification"
createdAt: "2026-08-12T00:00:00Z"
updatedAt: "2026-08-12T00:00:00Z"
tags: [domain, taxonomy, source-type, file-role, racochu]
see_also:
  - "adrs/0013-racochu-source-enrichment.adr.md"
  - "concepts/0007-file-metadata-layer.concept.md"
---

# Concept: Source Type Taxonomy and File Role Classification

## What

Two orthogonal taxonomies classify files in the bensyne system:

**Source Type** — where the file came from:
- `agent-session` — files from agent sessions (session.md, artifacts, etc.)
- `obsidian` — files from Obsidian vaults
- `per-repo-vault` — files from per-repo vaults (`.vault/`)

**File Role** — what kind of file it is (aligned with racochu):
- `config` — configuration files (package.json, tsconfig.json, .env, etc.)
- `code` — source code files (.ts, .js, .py, .rs, etc.)
- `docs` — documentation files (.md, .txt, .rst, etc.)

## Why

Source type determines how racochu processes and enriches the file (chunking strategy, relation composition). File role determines how bensyne treats the file for search and enrichment purposes. The separation allows bensyne to accept unified metadata from any source while racochu handles source-specific logic.

## Key Details

- Source type is a required field on File entities
- File role is optional (defaults based on file extension in racochu)
- Source type drives racochu's enrichment pipeline (see ADR-0013)
- File role is used in search filtering (searchFiles tool)
- Additional source types can be added without modifying bensyne (racochu is responsible for source-specific logic)
