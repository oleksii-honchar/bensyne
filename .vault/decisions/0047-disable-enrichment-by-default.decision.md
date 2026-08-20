---
type: decision
id: DEC-0047
system: racochu
title: "Disable Enrichment Pipeline by Default"
status: accepted
createdAt: "2026-08-09T19:30:00Z"
updatedAt: "2026-08-20T13:49:01Z"
tags: [enrichment, search, performance, config]
supersedes: []
superseded_by: []
see_also: [
  "decisions/0042-custom-llm-provider-mastra-llm-parameter.decision.md",
  "decisions/0043-non-fatal-enrichment-graceful-degradation.decision.md",
  "decisions/0059-llm-summary-producer-edges-population.decision.md",
  "concepts/0021-llm-enrichment.concept.md",
  "memories/0019-enrichment-metadata-not-indexed.memory.md"
]
---

# DEC-0047: Disable Enrichment Pipeline by Default

## Context

The LLM enrichment pipeline (extractMetadata) successfully extracts title and keywords from documents and stores them in the `metadata_json` field. However, investigation revealed that the Mnemosyne recall system does **not** index `metadata_json` — it only searches:

1. FTS5 index on `content` field
2. Vector embeddings from `memory_embeddings` table
3. Importance score
4. Temporal factors

The enriched metadata (mastraDocTitle, mastraDocKeywords) is dead data: stored but never used for retrieval. The enrichment pipeline adds LLM call latency (4+ minutes when API key is missing) without delivering any search improvement.

## Decision

**Disable enrichment by default.** The `enrichment.enabled` config flag defaults to `false` until a viable strategy exists for making enriched metadata useful for search.

This is **not** a permanent decision — the enrichment infrastructure is sound, and the LLM integration works. The blocker is the Mnemosyne-side gap: `metadata_json` is not indexed. The alternatives below outline paths to re-enable enrichment.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected (for now) |
|-------------|------|------|----------------------|
| **Disable enrichment (CHOSEN)** | Zero wasted latency; no dead data | No semantic metadata on chunks | Accepted as interim |
| **Append metadata to content** | Quick fix — FTS5 picks it up | Pollutes content field; embeddings include metadata noise | Not selected — too hacky |
| **Create FTS5 index on metadata** | Clean separation; targeted search | Requires Mnemosyne schema change | Better long-term path |
| **Update Mnemosyne recall** | Best — search metadata_json properly | Requires upstream changes to bensyne/mnemosyne | Best long-term path |

## Consequences

- **Positive:** No wasted LLM calls; no latency penalty; no dead data accumulation
- **Negative:** Chunks lack semantic metadata; search quality not enhanced by enrichment
- **Neutral:** Enrichment config and infrastructure remain in place; can be re-enabled once `metadata_json` is indexed
- **Re-evaluation trigger:** When Mnemosyne supports indexing `metadata_json` or we adopt a strategy that makes metadata searchable

## Verified in Code

- ⚠️ **Unverified:** Whether `enrichment.enabled` default is currently `true` or `false` in the running config — the config schema and runtime behavior need a code-level check
- ✅ The enrichment pipeline is gated by `enabled && llmUrl && apiKey` AND guard in MastraChunkingService
- ✅ Non-fatal error handling: enrichment failure logs warning, chunks proceed (DEC-0043)

## Reconciliation Note (2026-08-20, DEC-0059)

The **"dead data" caveat is scoped to Mnemosyne `metadata_json` search** — the bensyne-mcp
**file layer consumer is unaffected** and now consumes the LLM whole-file summary
(`files.summary` column, `summary_chain`, `related_files[].summary`, `summary_only`).
This decision's default (`enabled: false`) remains the shipped default; dev runs with
`enrichment.enabled: true` (dev.yaml) and the enrichment call now produces a real summary
per document (DEC-0059). Re-evaluation trigger unchanged for Mnemosyne-side metadata search.
See [[0059-llm-summary-producer-edges-population]].
