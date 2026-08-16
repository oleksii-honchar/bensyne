---
type: concept
system: shared
title: "Bensyne Bundle Cornerstone"
createdAt: "2026-08-16T18:05:00Z"
updatedAt: "2026-08-16T18:05:00Z"
tags: [cornerstone, architecture, bundle, file-based-sources, recall-enrichment]
see_also:
  - concepts/0007-file-metadata-layer.concept.md
  - concepts/0005-source-type-file-role.concept.md
  - concepts/0012-processing-model.concept.md
  - concepts/0009-file-role.concept.md
  - specifications/0002-file-metadata-layer.spec.md
---

# Concept: Bensyne Bundle Cornerstone

Canonical cornerstone description of the whole Bensyne application bundle (user directive, 2026-08-16). The single reference for what the bundle is, why it exists, and how recall-time enrichment must work.

## Bundle

The monorepo consists of two applications. Both follow hexagonal DDD with the use-case extension pattern. Both have end-to-end tests involving real service interaction.

- **Racochu** — a file watcher with multiple strategies for processing custom sources.
- **Bensyne MCP** — wraps Mnemosyne as the final target for chunked memories, both file-based and non-file-based.

## Purpose

Listen to multiple source types, process them according to each source's specificity, and store the relationships between files on the Bensyne MCP side.

**Why the intermediate layer exists:** Mnemosyne cannot store metadata inside a memory and cannot connect chunks/memories based on that metadata. So the chunking strategies (racochu) are extended to extract the corresponding metadata from each source and push it for processing via the Bensyne MCP tools.

On the Bensyne MCP side there is an intermediate layer before Mnemosyne (the storage) which stores files, chunks, and metadata relations. It applies and extends the original memory-only MCP tooling to file-based search and tooling; the server must preserve the existing indexing and searching capabilities, picking from the original Mnemosyne RAG toolset the tools that best match file-based search and edges-resolution needs.

## File-Based Sources (AgentSession, Obsidian, …)

All memories from a file-based source are file chunks, and every chunk carries corresponding metadata — each source has its own metadata set. When a chunk is remembered:

1. The metadata is stored near the file.
2. The connection (relation) between the files is built.

## Recall Flow for File-Based Sources

1. Recall first hits the mnemosyne side, which represents chunks and retrieves the best-guessed chunk for the request.
2. The chunk is then **enriched** — the most important part for file-based sources — according to the chunk's **source type**:
   - **AgentSession:** the chunk is reached by its nearby relationships to session materials — the session itself, specifications, findings, decisions, etc. Resolving a chunk with its relationships gives the agent a very rich result set to reason upon.
   - **Obsidian:** provide a summarized relationship of connected nodes. On request, a chunk can be enriched to: the whole file content, only the neighboring chunk (surrounding context), or the full content of the related files.

Result: an agent can traverse custom sources based on their relationships.
