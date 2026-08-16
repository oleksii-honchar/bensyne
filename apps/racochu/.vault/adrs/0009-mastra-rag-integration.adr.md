---
type: adr
id: ADR-0009
title: "Mastra RAG Integration"
status: accepted
createdAt: "2026-07-30T23:00:00Z"
updatedAt: "2026-07-31T07:30:00Z"
tags: [infrastructure, chunking, dependency]
see_also: ["concepts/0006-mastra-chunking-strategies.concept.md"]
---

# ADR-0009: Mastra RAG Integration

## Context

Need to implement chunking strategies for different content types (markdown, code, config, text). Building custom chunkers would be reinventing the wheel.

## Decision

Use `@mastra/rag` (v2.4.2 in package.json) for chunking via `MastraChunkingService` (src/application/strategies/mastra-chunking.service.ts). All custom chunkers removed — replaced with Mastra MDocument integration.

**Verified in code:**
- `MDocument.fromMarkdown()`, `MDocument.fromJSON()`, `MDocument.fromHTML()`, `MDocument.fromText()` — type-aware factories
- Strategies: `chunkMarkdown()`, `chunkRecursive()`, `chunkJSON()`, `chunkSentence()` — selected by `determineStrategy(filePath)`

## Alternatives Considered

1. **Custom chunkers** — Build own implementation
2. **LangChain** — Another popular choice but more complex
3. **LlamaIndex** — Heavyweight solution for this use case

## Consequences

- **Positive**: Production-ready chunking, better Unicode/language support, community maintained
- **Negative**: External dependency, learning curve for Mastra API
- **Mitigation**: Thin integration layer in MastraChunkingService — easy to swap if needed
