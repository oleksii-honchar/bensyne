---
type: adr
id: ADR-0005
title: "Hybrid Tag Generation"
status: accepted
createdAt: "2026-07-30T23:00:00Z"
updatedAt: "2026-07-31T07:30:00Z"
tags: [enhancement, tags]
see_also: ["concepts/0003-enhancement-pipeline.concept.md"]
---

# ADR-0005: Hybrid Tag Generation

## Context

Need to generate relevant tags for content organization and retrieval.

## Decision

Hybrid tag generation via `TagExtractionService` (src/application/services/tag-extraction.service.ts): content extraction (keywords, file role tags, path-derived tags) with optional LLM enhancement when `enrichment.enabled=true` and LLM is configured. Max 10 tags per chunk (configurable via `enhancement.tags.maxTags`).

## Alternatives Considered

1. **Pure content extraction** — Only extract tags from content
2. **Pure LLM generation** — Only use AI for tag generation
3. **Manual tagging** — Require manual tag assignment

## Consequences

- **Positive**: High-quality tags, works without external dependencies by default
- **Negative**: LLM dependency when enabled, additional complexity
- **Mitigation**: Robust fallback — LLM disabled by default, extraction always works
