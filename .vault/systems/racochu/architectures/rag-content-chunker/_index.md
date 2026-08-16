---
type: architecture
title: "RAG Content Chunker — System Overview"
system: rag-content-chunker
createdAt: "2026-07-31T07:30:00Z"
updatedAt: "2026-07-31T07:30:00Z"
tags: [architecture, overview]
see_also: ["adrs/0008-remote-database-segregation.adr.md"]
---

# RAG Content Chunker — System Overview

DDD-based NestJS CLI server for semantic content chunking before embedding ingestion to Mnemosyne MCP.

**Technology:** Node.js >=26, TypeScript, NestJS 11, Mastra RAG 2.4.2, Zod, Pino, Chokidar

**Start command:** `npx rag-content-chunker` (production), `npm run start:dev` (development)

**Config:** `~/.config/rag-content-chunker.yaml` (production), `dev.yaml` (development)

## C4 Levels

- [[containers/0001-server-container]] — Container level: single NestJS server + Mnemosyne MCP + remote SQLite databases
- [[components/0001-server-components]] — Component level: FileWatcher, MastraChunking, EnhancementPipeline, MnemosyneClient
- [[code/0001-domain-aggregates]] — Code level: Chunk, FileChange, WatchSource domain entities
