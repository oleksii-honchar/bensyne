---
type: decision
id: DEC-0016
system: bensyne-mcp
title: "Source-Type Enrichment in Racochu (Not Bensyne)"
status: accepted
createdAt: "2026-08-12T00:00:00Z"
updatedAt: "2026-08-12T00:00:00Z"
tags: [racochu, source-enrichment, architecture, bensyne, cross-system]
supersedes: []
superseded_by: []
see_also:
  - concepts/0005-source-type-file-role.concept.md
  - concepts/0007-file-metadata-layer.concept.md
---

# DEC-0016: Source-Type Enrichment in Racochu (Not Bensyne)

## Context

Source-type-specific enrichment (Obsidian backlink parsing, agent session structure mapping, chunking strategies) can happen either in bensyne or in racochu. The decision affects the complexity distribution between the two systems.

## Decision

Racochu handles source-specific enrichment; bensyne accepts unified metadata and remains source-agnostic.

## Racochu Responsibilities

- Source-specific chunking strategies
- File relationship composition per source type
- Metadata extraction and normalization
- Obsidian backlink parsing
- Agent session structure mapping

## Bensyne Responsibilities

- Accept unified file metadata
- Store in consistent format regardless of source
- Provide file-aware MCP tools for retrieval

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|--------------|
| **Racochu enrichment (chosen)** | Bensyne simple, source-agnostic, easier to add new source types | Racochu more complex | — |
| **Bensyne enrichment** | Centralized logic | Bensyne coupled to sources, harder to evolve | Breaks bensyne's source-agnostic design |
| **Split responsibilities** | Balanced | Complex integration, unclear boundaries | Adds complexity without clear benefit |

## Consequences

- **Positive:** Bensyne remains simple and source-agnostic; new source types don't require bensyne changes
- **Negative:** Racochu bears more complexity
- **Neutral:** Clear boundary between services
