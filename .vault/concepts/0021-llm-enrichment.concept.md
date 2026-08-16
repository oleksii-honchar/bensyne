---
type: concept
system: racochu
title: "LLM Enrichment"
createdAt: "2026-08-08T10:50:00Z"
updatedAt: "2026-08-09T19:30:00Z"
tags: [enrichment, llm, mastra, metadata]
see_also: [
  "decisions/0042-custom-llm-provider-mastra-llm-parameter.decision.md",
  "decisions/0043-non-fatal-enrichment-graceful-degradation.decision.md",
  "decisions/0047-disable-enrichment-by-default.decision.md",
  "concepts/0006-mastra-chunking-strategies.concept.md",
  "specifications/0002-enrichment-pipeline.spec.md",
  "memories/0012-enrichment-metadata-not-indexed.memory.md"
]
---

# Concept: LLM Enrichment

## What

LLM Enrichment extracts semantic metadata (title, keywords) from document content before chunking, using Mastra's `extractMetadata()` with a custom LLM provider pointing to a self-hosted litellm instance.

## Why

⚠️ **Current status: DISABLED by default.** The original rationale — that enriched metadata provides additional retrieval signals — is incorrect. The Mnemosyne recall system does not index the `metadata_json` field where enriched metadata is stored. See [[memories/0019-enrichment-metadata-not-indexed.memory]] for details and [[decisions/0047-disable-enrichment-by-default.decision]] for the decision to disable.

## Key Details

- **Implementation:** `LlmClientFactory.createCustomLlm()` creates a custom LLM via `@ai-sdk/openai` with `baseURL` pointing to litellm
- **Integration:** Custom LLM passed to `extractMetadata({ title: { llm }, keywords: { llm } })` — single call per document, metadata attached to all chunks
- **Configuration:** `enrichment.enabled`, `enrichment.llmUrl`, `enrichment.llmModel`, `enrichment.apiKey` — all three must be set (AND guard); `enabled` defaults to `false` per DEC-0047
- **Output:** `mastraDocTitle` and `mastraDocKeywords` metadata keys on every chunk — stored in `metadata_json` but **NOT indexed for search**
- **Error handling:** Non-fatal — LLM failure logs warning, chunks proceed without metadata
- **Superseded approach:** Original custom LiteLLMHttpClient + EnrichmentGatewayService removed; Mastra's built-in `extractMetadata()` with custom LLM is the current approach

## ⚠️ Critical Caveat

The enriched metadata is stored but **not used for search**. Mnemosyne recall only searches:
- `content` field (FTS5)
- `memory_embeddings` table (vector similarity)

The `metadata_json` field is a storage field, not a search field. Enrichment adds latency (LLM call per document) without improving retrieval. See [[memories/0019-enrichment-metadata-not-indexed.memory]] and [[decisions/0047-disable-enrichment-by-default.decision]].
