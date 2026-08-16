---
type: decision
id: DEC-0019
system: racochu
title: "Content-Aware Enhancement Architecture"
status: accepted
createdAt: "2026-07-30T23:00:00Z"
updatedAt: "2026-07-31T07:30:00Z"
tags: [enhancement, architecture]
see_also: [concepts/0010-enhancement-pipeline.concept.md]
---

# DEC-0019: Content-Aware Enhancement Architecture

## Context

The RAG Content Chunker needed enhancement features (character limits, importance scoring, tag generation, source extraction) while respecting content types and maintaining existing functionality.

## Decision

Integrate enhancements directly into the chunking engine with content-aware processing via `EnhancementPipelineService` (src/application/services/enhancement-pipeline.service.ts).

## Alternatives Considered

1. **Separate enhancement pipeline** — Post-processing after chunking
2. **Decorator pattern** — Wrap existing chunker with enhancement decorators
3. **Monolithic enhancement** — Single component handling all enhancements

## Consequences

- **Positive**: Better content handling, simpler architecture
- **Negative**: More complex chunking logic
- **Mitigation**: Clear service boundaries via EnhancementPipelineService orchestrating ImportanceScoringService and TagExtractionService
