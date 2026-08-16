---
type: index
title: "Decisions"
createdAt: "2026-08-16"
updatedAt: "2026-08-16"
tags: []
---

# Decisions

Architectural decisions for the Bensyne monorepo. Single ID space: `DEC-NNNN` (0001–0047). Grouped by `system` frontmatter.

### Shared

- [[0001-namespace-registration-protocol]] — Memory Bank Registration Protocol
- [[0002-namespace-parameter-enforcement]] — Memory Bank Parameter Enforcement
- [[0003-in-memory-namespace-registry]] — In-Memory Memory Bank Registry

### bensyne-mcp

- [[0004-namespace-registration-tool]] — Namespace Registration Tool
- [[0005-namespace-parameter-enforcement]] — Namespace Parameter Enforcement
- [[0006-in-memory-namespace-registry]] — In-Memory Namespace Registry
- [[0007-namespace-enforcement-breaking-change]] — Namespace Enforcement — Breaking Change Strategy
- [[0008-sqlite-hash-index]] — Use SQLite HashIndex for File Hash Deduplication
- [[0009-rotating-file-handler-logging]] — RotatingFileHandler for Application Logging
- [[0010-ddd-migration-approach]] — Python DDD Migration Approach
- [[0011-result-pattern-error-handling]] — Result Pattern for Error Handling
- [[0012-pydantic-validation]] — Pydantic for Data Validation
- [[0013-sqlite-file-metadata-storage]] — SQLite per Bank for File Metadata Storage
- [[0014-standalone-file-entities]] — Standalone File Entities (Not Embedded in Memory)
- [[0015-file-specific-mcp-tools]] — File-Specific MCP Tools Alongside Memory Tools
- [[0016-racochu-source-enrichment]] — Source-Type Enrichment in Racochu (Not Bensyne)
- [[0017-file-content-reconstruction]] — File Content Reconstruction from Chunks with chunk_index Ordering
- [[0018-on-conflict-do-update]] — Safe File Upserts — session.merge() over INSERT OR REPLACE

### racochu

- [[0019-content-aware-enhancement-architecture]] — Content-Aware Enhancement Architecture
- [[0020-content-aware-character-limits]] — Content-Aware Character Limits
- [[0021-selective-summarization-strategy]] — Selective Summarization Strategy
- [[0022-importance-scoring-algorithm]] — Importance Scoring Algorithm
- [[0023-hybrid-tag-generation]] — Hybrid Tag Generation
- [[0024-source-information-formatting]] — Source Information Formatting
- [[0025-configuration-management]] — Configuration Management
- [[0026-remote-database-segregation]] — Remote Database Segregation
- [[0027-mastra-rag-integration]] — Mastra RAG Integration
- [[0028-file-memory-tracking-prisma-sqlite]] — File→Memory Tracking with Prisma SQLite
- [[0029-namespace-registration-on-startup]] — Namespace Registration on Startup
- [[0030-namespace-parameter-enforcement]] — Namespace Parameter Enforcement
- [[0031-in-memory-namespace-registry]] — In-Memory Namespace Registry
- [[0032-array-based-memory-id-storage]] — Array-Based Memory ID Storage
- [[0033-aggregate-repository-service-pattern]] — Aggregate-Repository-Service Pattern
- [[0034-custom-chunking-strategies-framework]] — Custom Chunking Strategies Framework
- [[0035-obsidian-note-chunking-strategy]] — Obsidian Note Chunking Strategy
- [[0036-forget-after-ingest-on-file-update]] — Forget After Ingest on File Update
- [[0037-continue-on-forget-failure]] — Continue on Forget Failure — Don't Block Re-ingestion
- [[0038-no-tracker-api-changes]] — No Tracker API Changes Needed for File Update Flow
- [[0039-file-hash-deduplication-metadata]] — Use File Hash in Metadata for Deduplication
- [[0040-native-machine-id-hardware-detection]] — Use native-machine-id for Hardware ID Detection
- [[0041-filetracker-schema-extension]] — Add fileHash and hardwareId Fields to FileTracker Schema
- [[0042-custom-llm-provider-mastra-llm-parameter]] — Custom LLM Provider via Mastra's llm Parameter
- [[0043-non-fatal-enrichment-graceful-degradation]] — Non-Fatal Enrichment with Graceful Degradation
- [[0044-generic-frontmatter-preservation]] — Generic Frontmatter Preservation with Typed base Field
- [[0045-wikilink-extraction-graph-structure]] — Wikilink Extraction for Graph Structure
- [[0046-document-level-graph-metadata]] — Document-Level Graph Metadata on All Chunks
- [[0047-disable-enrichment-by-default]] — Disable Enrichment Pipeline by Default
