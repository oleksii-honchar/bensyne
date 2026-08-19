---
type: specification
id: SPEC-0001
system: racochu
title: "Enhancement Specification — Character Limits, Importance Scoring, Tag Generation"
kind: feature
status: in-progress
createdAt: "2026-07-30T22:45:00Z"
updatedAt: "2026-07-31T07:30:00Z"
tags: [enhancement, mnemosyne]
see_also: [
  "decisions/0019-content-aware-enhancement-architecture.decision.md",
  "decisions/0027-mastra-rag-integration.decision.md",
  "concepts/0010-enhancement-pipeline.concept.md"
]
---

# SPEC-0001: Enhancement Specification

## Goal

Enhance RAG Content Chunker to produce high-quality memories for Mnemosyne MCP: enforce character limits, score importance, extract tags, and format source attribution — all via Mastra RAG integration.

## Architecture

**Flow:** FileWatcher → MastraChunkingService → EnhancementPipelineService → MnemosyneClient → Mnemosyne MCP

**Key services (verified in src/):**
- `MastraChunkingService` — MDocument-based chunking with type-aware strategy selection
- `EnhancementPipelineService` — orchestrates ImportanceScoringService and TagExtractionService
- `ImportanceScoringService` — rule-based scoring with configurable factors
- `TagExtractionService` — content extraction with optional LLM enhancement
- `MnemosyneClient` — Streamable HTTP MCP client (Streamable HTTP transport, not SSE)

## Phases

### Phase 1: Core Infrastructure (COMPLETED)
- [x] Mastra RAG integration replacing custom chunkers
- [x] Enhancement pipeline service
- [x] Configuration schema with enhancement settings

### Phase 2: Enhancement Services (COMPLETED)
- [x] Importance scoring (35 tests)
- [x] Tag extraction (37 tests)
- [x] Enhancement pipeline wiring (16 tests)

### Phase 3: Integration (COMPLETED)
- [x] MnemosyneClient namespace/importance/tags support (28 tests)
- [x] Full flow: ProcessFileUseCase → ChunkContentUseCase → IngestChunkUseCase → MnemosyneClient

### Phase 4: Future (PROPOSED)
- [ ] Summarization for oversized prose
- [ ] LLM-based importance refinement
- [ ] PostgreSQL migration for >500K memories

## Success Criteria

| Criteria | Status |
|----------|--------|
| Character limits enforced per content type | ✅ Implemented via Mastra config |
| Importance scoring | ✅ Implemented (rule-based) |
| Tag extraction | ✅ Implemented (content-based + optional LLM) |
| Source attribution | ✅ Implemented via namespace + metadata |
| 415 unit tests passing | ✅ Verified |
| 6 e2e tests passing | ✅ Verified |

## Risks

- **SQLite scalability:** Mnemosyne SQLite supports ~500K memories; PostgreSQL migration path proposed but not implemented
- **LLM dependency:** Optional enrichment requires LLM endpoint; disabled by default

## References

- Session spec: `specifications/spec-mastra.md`
- DECs: DEC-0019 through DEC-0027
