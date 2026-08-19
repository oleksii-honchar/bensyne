---
type: decision
id: DEC-0043
system: racochu
title: "Non-Fatal Enrichment with Graceful Degradation"
status: accepted
createdAt: "2026-08-08T10:50:00Z"
updatedAt: "2026-08-08T10:50:00Z"
tags: [enrichment, error-handling, resilience]
supersedes: []
superseded_by: []
see_also: [
  "decisions/0042-custom-llm-provider-mastra-llm-parameter.decision.md",
  "concepts/0021-llm-enrichment.concept.md"
]
---

# DEC-0043: Non-Fatal Enrichment with Graceful Degradation

## Context

LLM calls are inherently unreliable (network issues, timeouts, rate limits, model unavailability). The enrichment feature must not block the chunking pipeline — a failing enrichment should not cause chunks to be lost.

## Decision

Enrichment failures are non-fatal:
- `try/catch` around `extractMetadata()` in MastraChunkingService
- On failure: `logger.warn()` with error details
- Chunks generated without enriched metadata and proceed normally
- No retries — log and move on

**Verified in code:**
- `src/application/strategies/mastra-chunking.service.ts` — try/catch with `logger.warn()` on enrichment failure
- E2E test: `enrichment-failure-non-fatal.e2e.test.ts` — verifies chunking continues when LLM fails

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| **Fatal error** | Ensures enrichment works | Blocks all chunking on LLM failure | Rejected |
| **Retry with backoff** | Handles transient failures | Adds complexity, delays chunking | Rejected |
| **Non-fatal (CHOSEN)** | Simple, reliable | Some documents may lack enriched metadata | Accepted |

## Consequences

- **Positive:** Chunking always completes; no cascading failures; simple error handling
- **Negative:** Some documents may lack enriched metadata; no automatic recovery
- **Mitigation:** Failed enrichment logged for operator awareness; document re-ingested on next change event
