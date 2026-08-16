---
type: architecture
title: "RAG Content Chunker — System Overview"
system: racochu
createdAt: "2026-07-31T07:30:00Z"
updatedAt: "2026-08-16"
tags: [architecture, overview]
see_also: [decisions/0026-remote-database-segregation.decision.md]
---

# Racochu — System Overview

DDD-based NestJS CLI server for semantic content chunking before embedding ingestion to Mnemosyne MCP.

**Technology:** Node.js >=26, TypeScript, NestJS 11, Mastra RAG 2.4.2, Zod, Pino, Chokidar

## C4 Levels

- [[containers/0001-server-container.container]] — Container level: single NestJS server + Mnemosyne MCP + remote SQLite databases
- [[components/0001-server-components.component]] — Component level: FileWatcher, MastraChunking, EnhancementPipeline, MnemosyneClient
- [[code/0001-domain-aggregates.code]] — Code level: Chunk, FileChange, WatchSource domain entities
