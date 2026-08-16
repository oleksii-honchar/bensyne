---
type: index
title: "Architecture Decision Records"
createdAt: "2026-07-31T07:30:00Z"
updatedAt: "2026-08-09T19:30:00Z"
tags: []
---

# Architecture Decision Records

Curated list of architectural decisions for RAG Content Chunker.

## Nodes

### Enhancement Architecture

- [[0001-content-aware-enhancement-architecture]] — Integrated enhancement features (limits, scoring, tags) directly into chunking engine
- [[0002-content-aware-character-limits]] — Per-content-type character limits with selective summarization
- [[0003-selective-summarization-strategy]] — Rule-based summarization only for prose/documentation
- [[0004-importance-scoring-algorithm]] — Rule-based importance scoring with configurable factors
- [[0005-hybrid-tag-generation]] — Hybrid tag generation combining content extraction with LLM assistance
- [[0006-source-information-formatting]] — Comprehensive source information extraction from namespace

### Infrastructure

- [[0007-configuration-management]] — Extended existing Zod config schema with enhancement settings
- [[0008-remote-database-segregation]] — Server-side namespace routing to separate SQLite databases per source
- [[0009-mastra-rag-integration]] — Use @mastra/rag library instead of custom chunkers

### File→Memory Tracking

- [[0010-file-memory-tracking-prisma-sqlite]] — Add Prisma SQLite for local file→memory relationship tracking
- [[0014-array-based-memory-id-storage]] — Store memory IDs as JSON array in single field per file
- [[0015-aggregate-repository-service-pattern]] — Use aggregate root pattern with repository and service for file→memory tracking

### Namespace Management

- [[0011-namespace-registration-on-startup]] — Register namespaces with descriptions on application bootstrap
- [[0012-namespace-parameter-enforcement]] — Make namespace parameter required for all memory tools
- [[0013-in-memory-namespace-registry]] — Use in-memory registry for namespace descriptions (no persistence)

### Chunking Strategies

- [[0016-custom-chunking-strategies-framework]] — Source-kinded strategy selection with ChunkingStrategy interface and StrategyRouter
- [[0017-obsidian-note-chunking-strategy]] — Obsidian note-aware chunking with frontmatter extraction and tag merging

### File Update Flow

- [[0018-forget-after-ingest-on-file-update]] — Forget-after-ingest on file change: separate handlers, forget old memories after new content is safely ingested
- [[0019-continue-on-forget-failure]] — Forget failures are non-fatal: continue on failure, retry on next change event
- [[0020-no-tracker-api-changes]] — Existing FileMemoryTrackerService API is sufficient for update flow (no new methods needed)

### File Hash Deduplication

- [[0021-file-hash-deduplication-metadata]] — Use SHA-256 file hash in metadata for cross-device deduplication
- [[0022-native-machine-id-hardware-detection]] — Use native-machine-id for hardware ID detection with fallback
- [[0023-filetracker-schema-extension]] — Add fileHash and hardwareId fields to FileTracker schema

### LLM Enrichment

- [[0024-custom-llm-provider-mastra-llm-parameter]] — Custom LLM via Mastra's llm parameter with @ai-sdk/openai (supersedes custom LiteLLM gateway)
- [[0025-non-fatal-enrichment-graceful-degradation]] — Enrichment failures are non-fatal: chunks proceed without metadata, logged for awareness
- [[0029-disable-enrichment-by-default]] — Disable enrichment by default: Mnemosyne doesn't index metadata_json, enriched data is dead

### Obsidian Frontmatter + Wikilinks

- [[0026-generic-frontmatter-preservation]] — Generic frontmatter preservation with typed base field and properties map
- [[0027-wikilink-extraction-graph-structure]] — Wikilink extraction for graph structure via pure regex utility
- [[0028-document-level-graph-metadata]] — Document-level metadata (base, properties, wikilinks) attached to all chunks
