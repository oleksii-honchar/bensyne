---
type: concept
title: "Mastra Chunking Strategies"
createdAt: "2026-07-31T07:30:00Z"
updatedAt: "2026-08-06T12:00:00Z"
tags: [chunking, mastra]
see_also: ["adrs/0009-mastra-rag-integration.adr.md", "concepts/0002-file-role.concept.md", "concepts/0009-chunking-strategy-pattern.concept.md", "concepts/0014-llm-enrichment.concept.md", "adrs/0024-custom-llm-provider-mastra-llm-parameter.adr.md"]
---

# Concept: Mastra Chunking Strategies

## What

Mastra Chunking Strategies are the four chunking algorithms from `@mastra/rag` used by MastraChunkingService, selected automatically based on file type.

## Why

Different content structures require different splitting logic — using the right strategy preserves semantic coherence within chunks.

## Key Details

**Strategies (verified in MastraChunkingService.determineStrategy and applyChunking):**

| Strategy | File Types | MDocument Method | How It Works |
|----------|-----------|------------------|--------------|
| `markdown` | .md, .mdx, .markdown, .html | `chunkMarkdown()` | Splits by headers (#, ##, ###), respects section boundaries |
| `recursive` | Code files (.ts, .js, .py, etc.) | `chunkRecursive()` | Recursive splitting by separators (newlines, statements, blocks) |
| `json` | .json, .yaml, .yml, .toml, .env | `chunkJSON()` | Splits by top-level keys, keeps key-value coherence |
| `sentence` | .txt, .log, unknown | `chunkSentence()` | Sentence boundary detection, configurable min/max/target size |

**MDocument factories:**
- `MDocument.fromMarkdown()` — for markdown files
- `MDocument.fromJSON()` — for JSON files
- `MDocument.fromHTML()` — for HTML files
- `MDocument.fromText()` — default for everything else

**Character limits passed to Mastra natively:**
- maxSize, minSize (50% of max), targetSize (75% of max), overlap (25% of max)
- No post-chunk truncation — Mastra handles splitting within limits

**Metadata extraction (LLM Enrichment — optional):**
- `document.extractMetadata({ title: { llm: customLLM }, keywords: { llm: customLLM } })` — custom LLM created by LlmClientFactory via @ai-sdk/openai with custom baseURL
- Single call per document; metadata (`mastraDocTitle`, `mastraDocKeywords`) attached to all chunks
- Non-fatal: LLM failure logs warning, chunks proceed without metadata
- Guard: `enrichment.enabled && llmUrl && apiKey` (all three required)
- See [[0014-llm-enrichment]] and [[0024-custom-llm-provider-mastra-llm-parameter]]

**Strategy Framework Integration (as of 2026-08-06):**
- MastraChunkingService now implements `ChunkingStrategy` interface
- Routed via `StrategyRouter.selectStrategy()` when `sourceConfig.strategy === 'content-aware'` (default)
- Internal strategy selection (markdown/recursive/json/sentence) still uses file extension
- New strategies (`AgentSessionChunkingStrategy`, `ObsidianChunkingStrategy`) delegate to MastraChunkingService for body chunking
