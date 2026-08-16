---
type: decision
id: DEC-0042
system: racochu
title: "Custom LLM Provider via Mastra's llm Parameter"
status: accepted
createdAt: "2026-08-08T10:50:00Z"
updatedAt: "2026-08-08T10:50:00Z"
tags: [enrichment, mastra, llm, litellm]
supersedes: []
superseded_by: []
see_also: [
  "concepts/0014-llm-enrichment.concept.md",
  "memories/0009-mastra-extract-metadata-basellm-hardcoded.memory.md",
  "decisions/0027-mastra-rag-integration.decision.md"
]
---

# DEC-0042: Custom LLM Provider via Mastra's llm Parameter

## Context

Mastra's `extractMetadata()` hardcodes OpenAI as the default LLM at module load time:

```typescript
// Mastra source: packages/rag/src/document/extractors/types.ts
const openai = createOpenAI({ apiKey: process.env.OPENAI_API_KEY });
export const baseLLM = openai('gpt-4o');
```

All extractors default to `baseLLM`: `options?.llm ?? baseLLM`. This means:
- `OPENAI_BASE_URL` env var is NOT respected
- Self-hosted LLMs (litellm, llama.cpp) cannot be used without modification
- Racochu's enrichment was silently failing — config was correct but the hardcoded OpenAI endpoint was unreachable

Investigation of Mastra's source code revealed that **custom LLMs ARE supported** via the `llm` parameter on each extractor type:

```typescript
interface TitleExtractorsArgs {
  llm?: MastraLanguageModel;  // Custom language model
}

interface KeywordExtractArgs {
  llm?: MastraLanguageModel;  // Custom language model
}
```

## Decision

Create a `LlmClientFactory` that produces a custom OpenAI-compatible LLM using `@ai-sdk/openai` with our `baseURL` pointing to litellm:

```typescript
import { createOpenAI } from '@ai-sdk/openai';

const customOpenAI = createOpenAI({
  apiKey: enrichmentConfig.apiKey,
  baseURL: enrichmentConfig.llmUrl,  // e.g. https://lite-llm.lan/v1
});

const customLLM = customOpenAI(enrichmentConfig.llmModel);

// Pass to extractMetadata
enrichedDoc = await document.extractMetadata({
  title: { llm: customLLM },
  keywords: { llm: customLLM },
});
```

The `LlmClientFactory.createCustomLlm()` returns `MastraLegacyLanguageModel | MastraLanguageModel | null` — null when config is incomplete.

**Verified in code:**
- `src/infrastructure/services/llm-client-factory.ts` (22 lines)
- `src/application/strategies/mastra-chunking.service.ts` — custom LLM passed to `extractMetadata()`
- Guard condition: `enabled && llmUrl && apiKey` (all three required)
- Old `extractMetadata({ title: true, keywords: true })` call removed
- Old custom gateway code (`LiteLLMHttpClient`, `EnrichmentGatewayService`) removed

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| **Monkey-patch Mastra** | Minimal code change | Fragile, breaks on version upgrade | Rejected |
| **Skip enrichment** | Quick workaround | No enrichment — defeats purpose | Rejected |
| **Full custom gateway** (original approach) | Complete control | More code, duplicates Mastra functionality | Superseded by this ADR |
| **Mastra llm parameter (CHOSEN)** | Uses Mastra infrastructure, minimal code | Slightly more setup | Accepted |

## Consequences

- **Positive:** Enrichment works with self-hosted LLMs; minimal code changes; reuses Mastra's prompts and response parsing; not fragile (uses official parameter)
- **Negative:** Depends on Mastra's `llm` parameter remaining available; less control over prompts than full custom solution
- **Mitigation:** Thin LlmClientFactory — easy to swap implementation if needed
