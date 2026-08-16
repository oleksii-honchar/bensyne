---
type: index
title: "Domain Concepts"
createdAt: "2026-07-31T07:30:00Z"
updatedAt: "2026-08-08T10:50:00Z"
tags: []
---

# Domain Concepts

Core domain terminology and mental models for RAG Content Chunker.

## Nodes

### Chunking & Processing

- [[0001-chunk-concept]] — Chunk entity representing a semantically coherent content fragment
- [[0002-file-role]] — File classification (docs, code, config, agent-output) driving chunking strategy
- [[0005-processing-model]] — File watching → chunking → ingestion flow with bounded queue and dedup

### Enhancement

- [[0003-enhancement-pipeline]] — Post-chunking enhancement stages (importance, tags, namespace)
- [[0006-mastra-chunking-strategies]] — Mastra RAG strategy selection per file type
- [[0014-llm-enrichment]] — LLM enrichment via Mastra extractMetadata() with custom LLM provider

### Mnemosyne Integration

- [[0004-namespace-routing]] — Server-side namespace → database mapping for source segregation
- [[0007-file-memory-tracking]] — File→Memory relationship tracking via Prisma SQLite
- [[0008-namespace-management]] — Namespace lifecycle: registration, enforcement, discovery

### Strategy Framework

- [[0009-chunking-strategy-pattern]] — ChunkingStrategy interface and StrategyRouter pattern
- [[0010-agent-session-chunking]] — Session-aware chunking with frontmatter extraction and metadata enrichment
- [[0011-obsidian-note-chunking]] — Obsidian note chunking with frontmatter extraction and tag merging
- [[0012-session-metadata-service]] — Cached session.md metadata extraction with 5-minute TTL

### Deduplication

- [[0013-file-hash-deduplication]] — SHA-256 file hash deduplication for cross-device sync
