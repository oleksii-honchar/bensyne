---
type: concept
title: "Enhancement Pipeline"
createdAt: "2026-07-31T07:30:00Z"
updatedAt: "2026-07-31T07:30:00Z"
tags: [domain, enhancement]
see_also: ["adrs/0001-content-aware-enhancement-architecture.adr.md", "adrs/0004-importance-scoring-algorithm.adr.md", "adrs/0005-hybrid-tag-generation.adr.md"]
---

# Concept: Enhancement Pipeline

## What

The Enhancement Pipeline is a post-chunking processing stage that enriches raw Mastra chunks with importance scores, tags, and namespace assignment before ingestion.

## Why

Raw chunks lack metadata needed for effective retrieval: without importance, all memories surface equally; without tags, keyword search is limited; without namespace, sources cannot be segregated.

## Key Details

**Stages (src/application/services/enhancement-pipeline.service.ts):**

1. **Importance Scoring** — `ImportanceScoringService.score(chunk, config)`
   - Factors: fileRole (0.4), length (0.2), keywords (0.3), header (0.1)
   - Output: importance 0.0–1.0 on Chunk

2. **Tag Extraction** — `TagExtractionService.extract(chunk, config)`
   - Content-based: keyword extraction, file role tags, path-derived tags
   - Optional LLM enhancement if `enrichment.enabled=true`
   - Output: up to 10 tags on Chunk

3. **Namespace Assignment** — from source config (`watchSourceConfigSchema.namespace`)
   - Defaults to source id if not specified
   - Output: namespace on Chunk for server-side DB routing

**Resilience:** Each stage wrapped in try/catch — on error, logs and uses safe default (importance=0.5, tags=[], namespace=default), continues processing.

**Configured via:** `enhancement.importance.*`, `enhancement.tags.*`, `enrichment.*` in config schemas.
