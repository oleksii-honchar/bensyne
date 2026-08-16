---
type: specification
id: SPEC-0002
system: racochu
title: "Enrichment Pipeline Specification"
kind: feature
status: in-progress
createdAt: "2026-08-01T07:30:00Z"
updatedAt: "2026-08-01T07:30:00Z"
tags: [enrichment, mnemosyne, mastra-rag]
see_also: [
  "specifications/0001-enhancement-specification.spec.md",
  "concepts/0003-enhancement-pipeline.concept.md",
  "concepts/0006-mastra-chunking-strategies.concept.md",
  "concepts/0014-llm-enrichment.concept.md",
  "decisions/0022-importance-scoring-algorithm.decision.md",
  "decisions/0023-hybrid-tag-generation.decision.md",
  "decisions/0042-custom-llm-provider-mastra-llm-parameter.decision.md",
  "decisions/0043-non-fatal-enrichment-graceful-degradation.decision.md"
]
---

# SPEC-0002: Enrichment Pipeline Specification

## Goal

Define the enrichment pipeline that enhances raw chunks with semantic metadata (importance score, tags, source attribution) before ingestion into Mnemosyne MCP for improved RAG retrieval quality.

## Scope

Applies to all chunks produced by Mastra RAG chunking strategies before Mnemosyne ingestion.

## Architecture

**Enrichment Pipeline (EnhancementPipelineService):**
```
Raw Chunk → [ImportanceScoringService] → [TagExtractionService] → Enriched Chunk → MnemosyneClient
```

## Enrichment Stages

### Stage 1: Importance Scoring

**Service:** `ImportanceScoringService`  
**Algorithm:** Rule-based weighted scoring (configurable)

**Factors:**
| Factor | Weight | Source |
|--------|--------|--------|
| fileRole | 0.4 | FileRole enum (core_code, spec, decision, docs, config) |
| length | 0.2 | Character count (log-normalized) |
| keywords | 0.3 | Presence of importance keywords (verified, critical, TODO, BUG) |
| header proximity | 0.1 | Distance from nearest header |

**Output:** `importance: number` (0–1 scale)

### Stage 2: Tag Extraction

**Service:** `TagExtractionService`  
**Mode:** Hybrid — content extraction first, optional LLM enhancement

**Content-based extraction (always):**
- File extensions → tags (e.g., `.md` → markdown, `.ts` → typescript)
- File roles → tags (e.g., decision → architecture)
- Content keywords → tags (e.g., "Mnemosyne", "chunking")

**LLM-based extraction (optional):**
- Requires `ENHANCEMENT_LLM_ENDPOINT` and `ENHANCEMENT_LLM_MODEL`
- Configured via `config.enrichment.llm`

**Output:** `tags: string[]` (3–8 tags per chunk)

### Stage 3: Source Attribution

**Service:** `EnhancementPipelineService` (integrated)

**Extracted from:**
- Namespace path → source attribution (e.g., `agent-sessions/260728-...`)
- File path → source file reference
- Chunk index → position in file

**Output:** `source: string` (human-readable source attribution)

## Configuration

All enrichment settings defined in `src/infrastructure/config/config-schemas.ts`:

```yaml
enhancement:
  importanceScoring:
    enabled: true
    weights:
      fileRole: 0.4
      length: 0.2
      keywords: 0.3
      headerProximity: 0.1
    keywords:
      - verified
      - critical
      - TODO
      - BUG
      - NOTE
  tagExtraction:
    enabled: true
    llm:
      enabled: false  # Optional LLM enhancement
      endpoint: ""
      model: "qwen3.6-27b"
      maxTokens: 100
```

## Enriched Chunk Schema

All enrichment fields added to `Chunk.entity.ts`:

```typescript
interface EnrichedChunk {
  id: string;
  content: string;
  source: string;              // Stage 3 output
  importance: number;          // Stage 1 output
  tags: string[];              // Stage 2 output
  fileRole: FileRole;          // Input context
  fileKey: string;
  namespace: string;
  chunkIndex: number;
  totalChunks: number;
  metadata: Record<string, unknown>;
}
```

## Phases

### Phase 1: Core Enrichment (COMPLETED)
- [x] EnhancementPipelineService wiring
- [x] ImportanceScoringService with configurable weights
- [x] TagExtractionService with content-based extraction
- [x] Source attribution from namespace/path

### Phase 2: Integration (COMPLETED)
- [x] Pipeline integrated into ProcessFileUseCase → IngestChunkUseCase
- [x] MnemosyneClient passes importance/tags via serverParams
- [x] 35+ unit tests for enrichment services

### Phase 3: LLM Enrichment (COMPLETED — 2026-08-08)
- [x] LLM-based title extraction via Mastra extractMetadata() with custom LLM
- [x] LLM-based keyword extraction via Mastra extractMetadata() with custom LLM
- [x] Non-fatal error handling — enrichment failure doesn't block chunking
- [x] Custom LLM via @ai-sdk/openai with custom baseURL (litellm)
- [x] 712 tests passing (including 7 factory tests, 9 E2E tests)
- [ ] LLM-based tag refinement (future)
- [ ] LLM-based importance scoring refinement (future)
- [ ] Chunk summarization for oversized prose (future)

## Success Criteria

| Criteria | Status |
|----------|--------|
| Importance scoring produces 0–1 scores | ✅ Implemented |
| Tag extraction produces 3–8 tags per chunk | ✅ Implemented |
| Source attribution is human-readable | ✅ Implemented |
| Pipeline is fully configurable via YAML | ✅ Implemented |
| All enrichment is deterministic (no LLM dependency) | ✅ Implemented |
| 35+ unit tests for enrichment services | ✅ Implemented |

## Risks

- **LLM cost:** Optional LLM enhancement adds cost; disabled by default
- **False positives:** Keyword-based scoring may miss context-specific importance
- **Tag noise:** Content extraction may produce generic tags; LLM enhancement mitigates

## References

- DEC-0022: Importance scoring algorithm
- DEC-0023: Hybrid tag generation
- DEC-0024: Source information formatting
- Session spec: `specifications/spec-mastra.md`
