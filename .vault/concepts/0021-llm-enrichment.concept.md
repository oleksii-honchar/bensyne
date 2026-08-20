---
type: concept
system: racochu
title: "LLM Enrichment"
createdAt: "2026-08-08T10:50:00Z"
updatedAt: "2026-08-20T13:49:01Z"
tags: [enrichment, llm, mastra, metadata]
see_also: [
  "decisions/0042-custom-llm-provider-mastra-llm-parameter.decision.md",
  "decisions/0043-non-fatal-enrichment-graceful-degradation.decision.md",
  "decisions/0047-disable-enrichment-by-default.decision.md",
  "decisions/0059-llm-summary-producer-edges-population.decision.md",
  "concepts/0013-mastra-chunking-strategies.concept.md",
  "specifications/0004-enrichment-pipeline.spec.md",
  "memories/0019-enrichment-metadata-not-indexed.memory.md"
]
---

# Concept: LLM Enrichment

## What

LLM Enrichment extracts semantic metadata (title, keywords, whole-file summary) from document content before chunking, using Mastra's `extractMetadata()` with a custom LLM provider pointing to a self-hosted litellm instance.

## Why

The enriched metadata feeds the bensyne-mcp **file layer**: the whole-file summary is
persisted (`files.summary`) and surfaced on recall as `summary_chain` /
`related_files[].summary` (cornerstone "summarized relationship of connected nodes"), and
title/keywords appear in recall read enrichment. ⚠️ **Mnemosyne retrieval caveat:** the
Mnemosyne recall system itself does not index the `metadata_json` field where enriched
metadata is stored — see [[memories/0019-enrichment-metadata-not-indexed.memory]] and
[[decisions/0047-disable-enrichment-by-default.decision]] (caveat scoped to Mnemosyne
search; the file layer consumer is unaffected, DEC-0059).

## Key Details

- **Implementation:** `LlmClientFactory.createCustomLlm()` creates a custom LLM via `@ai-sdk/openai` with `baseURL` pointing to litellm
- **Integration:** Custom LLM passed to `extractMetadata({ title: { llm }, keywords: { llm }, summary: { llm } })` — single call per document, metadata attached to all chunks
- **Configuration:** `enrichment.enabled`, `enrichment.llmUrl`, `enrichment.llmModel`, `enrichment.apiKey` — all three must be set (AND guard); `enabled` defaults to `false` per DEC-0047, dev runs with `enabled: true`
- **Summary:** `mastraDocSummary` stamped on every chunk (DEC-0046 pattern); word cap `summaryMaxWords = clamp(floor(docMaxTokens/200), 20, 120)` (default 16000 → 80 words); DTO maps to wire `summary` (DEC-0059)
- **Output:** `mastraDocTitle`, `mastraDocKeywords`, `mastraDocSummary` metadata keys on every chunk — stored in `metadata_json` (Mnemosyne-side not indexed) AND consumed by the bensyne-mcp file layer
- **Error handling:** Non-fatal — LLM failure logs warning, chunks proceed without metadata
- **Superseded approach:** Original custom LiteLLMHttpClient + EnrichmentGatewayService removed; Mastra's built-in `extractMetadata()` with custom LLM is the current approach

## ⚠️ Critical Caveat

Enriched metadata stored in `metadata_json` is **not used for Mnemosyne search**. Mnemosyne
recall only searches `content` (FTS5), `memory_embeddings`, importance, and temporal factors.
The enrichment value flows through the **bensyne-mcp file layer** (read enrichment,
summaries, edges) — see [[decisions/0059-llm-summary-producer-edges-population]] and
[[memories/0019-enrichment-metadata-not-indexed.memory]].
