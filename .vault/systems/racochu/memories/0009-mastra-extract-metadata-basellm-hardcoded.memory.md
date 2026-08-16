---
type: memory
title: "Mastra extractMetadata() Hardcodes OpenAI baseLLM"
createdAt: "2026-08-08T10:50:00Z"
updatedAt: "2026-08-08T10:50:00Z"
tags: [mastra, llm, gotcha, enrichment]
see_also: [
  "adrs/0024-custom-llm-provider-mastra-llm-parameter.adr.md",
  "concepts/0014-llm-enrichment.concept.md"
]
---

# Memory: Mastra extractMetadata() Hardcodes OpenAI baseLLM

## Fact

Mastra's `extractMetadata()` creates a hardcoded OpenAI LLM at module load time: `createOpenAI({ apiKey: process.env.OPENAI_API_KEY })('gpt-4o')`. The `OPENAI_BASE_URL` environment variable is NOT respected — only `OPENAI_API_KEY` is read.

## Context

During enrichment feature investigation (2026-08-07), racochu's enrichment was silently failing despite correct config (enrichment enabled, valid litellm endpoint). Root cause: Mastra's default `baseLLM` points to `api.openai.com`, not our litellm proxy. Source code verified at `/Users/oleksii.honchar/www/misc/mastra/packages/rag/src/document/extractors/types.ts`.

## Impact

Without a custom LLM, enrichment silently fails — no metadata extracted, no error logged (because the default LLM throws an unhandled error that gets swallowed by Mastra's error handling). The fix is to pass a custom LLM via the `llm` parameter on each extractor type.
