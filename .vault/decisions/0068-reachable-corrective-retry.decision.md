---
type: decision
id: DEC-0069
system: racochu
title: "Reachable Corrective Retry via Post-Validation of Resolved Result"
status: accepted
createdAt: "2026-08-23T19:20:00Z"
updatedAt: "2026-08-23T20:23:00Z"
tags: [enrichment, error-handling, retry, mastra, testing]
supersedes: []
superseded_by: []
see_also: [
  "decisions/0067-per-chunk-enrichment-observability.decision.md",
  "decisions/0043-non-fatal-enrichment-graceful-degradation.decision.md",
  "decisions/0042-custom-llm-provider-mastra-llm-parameter.decision.md"
]
---

# DEC-0069: Reachable Corrective Retry via Post-Validation of Resolved Result (racochu)

## Context

Mastra `SchemaExtractor.extract` wraps each `agent.generate` in try/catch: on structured-output validation failure it logs `console.error("Schema extraction failed:", error)` and returns `{}` (`@mastra/rag@2.4.2 dist/index.cjs:4484`). `MDocument.extractMetadata` therefore RESOLVES — never rejects — on the exact failure mode T8 (corrective retry) and T10 (429 backoff) were built to handle. Result: failed chunks are silently stored un-enriched; the corrective retry is dead code for schema-validation failures. Tests mock `mockRejectedValueOnce` (mastra-chunking.service.test.ts:1347) — a contract real Mastra does not implement.

## Decision

1. **Post-validate the RESOLVED result** inside the `enrichChunk` attempt: new exported `assertExtractedEnrichment(enrichedDoc)` throws `EnrichmentValidationError` when `getDocs()[0].metadata.enrichment` is missing or not an object with string `title`/`keywords`/`summary`.
2. The throw lands in the EXISTING catch flow: not a rate-limit error → exactly ONE corrective retry (T8) with `ENRICHMENT_CORRECTIVE_RETRY_INSTRUCTION`; corrective attempt validated the same way; both-fail → existing WARN `ExtractMetadata failed` (now with the validation error + chunk position). Retry budget unchanged (≤3 LLM calls/chunk, no unbounded loop).
3. **Tests updated to the real library contract (R6):** corrective-retry tests mock resolve-empty (not reject) — red against current code, green after fix; e2e gains a resolve-empty case. Throw-based failure mocks remain valid (sync throw inside the async IIFE → rejection).
4. **Not changed this round:** T10 429 backoff stays as-is (SchemaExtractor swallows 429s too; T11 LiteLLM `num_retries:3` at the proxy is the primary 429 net). Server-side schema enforcement deferred (needs llama.cpp verification). See Open Decisions O1/O2.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|---|---|---|---|
| **Post-validate resolved result (CHOSEN)** | Minimal diff; reuses existing bounded retry; makes T8 reachable for the root-caused mode | Swallowed 429 misclassified as validation (bounded, harmless); T10 still not client-reachable | Accepted — matches user's observability-first ask |
| Bypass SchemaExtractor (direct `agent.generate`) | Makes BOTH T8 and T10 reachable | Rewrites the enrichment core; re-implements metadataKey stamping/prompt wiring; higher regression risk | Deferred — follow-up if 429-swallow resurfaces (O1) |
| Server-side schema (`response_format`/grammar) | Prevents partial JSON at source | llama.cpp json_schema silent-fallback issues; needs live verification | Deferred — O2 |
| Keep rejecting-only tests | Zero test churn | Tests green against a contract real Mastra doesn't implement | Rejected (R6) |

## Consequences

- **Positive:** Corrective retry (T8) becomes reachable for schema-validation failures — the failure mode from the 16:19 incident gets a real retry.
- **Positive:** Failed chunks are no longer silently un-enriched: post-validation failure surfaces as a WARN with error + chunk position.
- **Positive:** Tests now assert the real Mastra resolve-empty contract — regression protection.
- **Negative:** Behavior change: a resolved-empty extraction now triggers a corrective retry (bounded at 1) — intended, but changes log/retry counts vs today.
- **Neutral:** Swallowed 429s consume the corrective-retry budget instead of backoff (≤2 attempts) — accepted, T11 remains the primary net.
- **Neutral:** `assertExtractedEnrichment` mirrors the zod schema's shape check (title/keywords/summary strings); if the schema evolves, the helper must be kept in sync.
