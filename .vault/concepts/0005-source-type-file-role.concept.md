---
type: concept
system: shared
title: "Source Type Taxonomy and File Type Classification"
createdAt: "2026-08-12T00:00:00Z"
updatedAt: "2026-08-18T07:55:43Z"
tags: [domain, taxonomy, source-type, file-role, racochu]
see_also:
  - decisions/0016-racochu-source-enrichment.decision.md
  - decisions/0048-dual-hash-wire-contract.decision.md
  - concepts/0007-file-metadata-layer.concept.md
  - concepts/0009-file-role.concept.md
---

# Concept: Source Type Taxonomy and File Type Classification

## What

Two orthogonal taxonomies classify files in the bensyne system:

**Source Type** — WHO PRODUCED the file (D29, 2026-08-18; enum `SourceType` in bensyne `src/domain/models/file_model.py`, 1:1-mirrored by racochu `SOURCE_TYPES`):
- `obsidian` — Obsidian vault notes
- `agent-sessions` — agent session folders (plural: one folder holds multiple sessions)
- `vault` — the generic knowledge vault (was racochu's `content-aware` strategy; racochu default)
- `unknown` — NOT a producer: degrade-never-reject fallback for absent/invalid wire values

**File Type** — what kind of file it is (optional `file_type` string field, aligned with racochu):
- `config` — configuration files (package.json, tsconfig.json, .env, etc.)
- `code` — source code files (.ts, .js, .py, .rs, etc.)
- `docs` — documentation files (.md, .txt, .rst, etc.)

## Why

Source type determines how racochu chunks the file — **strategy ≡ source type** (D29): a racochu watch source's `source_type` field *is* its source type (renamed from `strategy`), one name end-to-end (config → chunk → wire → DB); the chunking layer is a `source_type → chunker` router. File type determines how bensyne treats the file for search purposes.

**1:1 lock:** the value set is declared once in contract v1 and mirrored 1:1 — bensyne `SourceType` enum (4 values) + bootstrap CHECK DDL, racochu `SOURCE_TYPES` + zod schema + chunk stamping, enforced by 2 asserting tests per app. Extension policy: a new value lands as a package — its ingestion chunker (strategy ≡ type) + both contract mirrors + both asserting tests + a post-bootstrap migration.

## Key Details

- Source type is a required field on File entities
- File type is optional (defaults based on file extension in racochu)
- Source type drives racochu's chunking pipeline (see DEC-0016)
- File type is used in search filtering (searchFiles tool `file_role` parameter)
- The old `SOURCE_TYPE_MAP` (mapping free-form source ids → enum) was **deleted** in D29 — it let chunks ship without a source type; the wire value is the enum value itself, stamped by the router
