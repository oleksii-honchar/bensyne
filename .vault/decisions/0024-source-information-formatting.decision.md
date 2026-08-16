---
type: decision
id: DEC-0024
system: racochu
title: "Source Information Formatting"
status: accepted
createdAt: "2026-07-30T23:00:00Z"
updatedAt: "2026-07-31T07:30:00Z"
tags: [enhancement, metadata]
see_also: [concepts/0011-namespace-routing.concept.md]
---

# DEC-0024: Source Information Formatting

## Context

Need to format source information for proper attribution and context in stored memories.

## Decision

Comprehensive source information stored in chunk metadata: filePath, sourceId, sectionHeader, breadcrumb, fileRole, language, chunkIndex, totalChunks. Source is derived from namespace (watch source id).

## Alternatives Considered

1. **Minimal source info** — Only include file path
2. **Maximal source info** — Include all available metadata
3. **Standardized format** — Use predefined source format

## Consequences

- **Positive**: Comprehensive traceability, adequate context for retrieval
- **Negative**: Increases memory payload size
- **Mitigation**: Selective inclusion via `enhancement.source.*` config flags
