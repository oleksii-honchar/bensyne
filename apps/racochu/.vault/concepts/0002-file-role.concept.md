---
type: concept
title: "File Role"
createdAt: "2026-07-31T07:30:00Z"
updatedAt: "2026-07-31T07:30:00Z"
tags: [domain, chunking]
see_also: ["concepts/0001-chunk-concept.concept.md", "concepts/0006-mastra-chunking-strategies.concept.md"]
---

# Concept: File Role

## What

File Role is the classification of a file that determines the chunking strategy and character limits applied to its content.

## Why

Different content types require different chunking approaches — code should respect syntax boundaries, config files should split per key, prose should respect sentence boundaries.

## Key Details

**Roles (src/domain/chunk.entity.ts):**

| Role | Extensions / Detection | Strategy | Max Chars |
|------|----------------------|----------|-----------|
| `DOCS` | .md, .markdown, .txt | markdown / sentence | 200 |
| `CODE` | .ts, .js, .py, .go, .java, .rs, etc. | recursive | 400 |
| `CONFIG` | .json, .yaml, .yml, .toml, .xml, .ini | json | 300 |
| `AGENT_OUTPUT` | Path includes `.agent-sessions` or `agent-meta-tool` | markdown | 300 |

**Detection order (MastraChunkingService.determineFileRole):**
1. Path pattern check (agent-sessions → AGENT_OUTPUT)
2. Extension check (config extensions → CONFIG, code extensions → CODE)
3. Default → DOCS

**Role affects:**
- Chunking strategy selection (`determineStrategy()`)
- Character limit (`getMaxCharacters()`)
- MDocument factory type (`determineDocumentType()`)
- Importance scoring (fileRole factor weight 0.4)
