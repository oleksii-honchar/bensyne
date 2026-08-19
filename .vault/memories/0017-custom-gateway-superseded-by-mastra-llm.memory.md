---
type: memory
system: racochu
title: "Custom LiteLLM Gateway Superseded by Mastra llm Parameter"
createdAt: "2026-08-08T10:50:00Z"
updatedAt: "2026-08-08T10:50:00Z"
tags: [enrichment, litellm, mastra, refactoring]
see_also: [
  "decisions/0042-custom-llm-provider-mastra-llm-parameter.decision.md",
  "concepts/0021-llm-enrichment.concept.md"
]
---

# Memory: Custom LiteLLM Gateway Superseded by Mastra llm Parameter

## Fact

The initial approach of building a custom `LiteLLMHttpClient` + `EnrichmentGatewayService` to bypass Mastra's `extractMetadata()` was superseded after source code investigation revealed Mastra supports custom LLMs via the `llm` parameter.

## Context

Two developer cycles: first built custom gateway (LiteLLMHttpClient with native fetch, AbortController timeout, JSON parsing with regex fallback, p-limit concurrency). Second cycle used Mastra's `llm` parameter with `@ai-sdk/openai` — much simpler, uses Mastra's infrastructure for prompts, response parsing, and error handling. Old code removed, new approach verified with 712 tests.

## Impact

Simpler implementation, fewer moving parts, less custom code to maintain. The custom gateway approach is documented as history but should not be considered the current pattern.
