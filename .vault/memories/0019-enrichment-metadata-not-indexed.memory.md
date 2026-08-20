---
type: memory
system: racochu
title: "Enrichment Metadata Not Indexed — Enrichment Pipeline Is Basically Useless"
createdAt: "2026-08-09T19:30:00Z"
updatedAt: "2026-08-20T13:49:01Z"
tags: [enrichment, search, mnemosyne, metadata, gotcha]
see_also: [
  "decisions/0047-disable-enrichment-by-default.decision.md",
  "decisions/0059-llm-summary-producer-edges-population.decision.md",
  "concepts/0021-llm-enrichment.concept.md"
]
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Memory: Enrichment Metadata Not Indexed — Enrichment Pipeline Is Basically Useless

## Fact

The Mnemosyne recall system does **not** search the `metadata_json` field. Enriched title and keywords extracted by the LLM enrichment pipeline are stored but never used for retrieval — the pipeline is basically useless for improving search quality.

## Context

Discovered during enrichment debugging session (ses_01862fe14ffeG0VDbh7QOgmiCf). The enrichment pipeline successfully extracts metadata:

```json
{
  "mastraDocTitle": "Machine Learning Fundamentals",
  "mastraDocKeywords": "machine learning, artificial intelligence, neural networks..."
}
```

But Mnemosyne recall only searches:
- `content` field (FTS5 full-text search)
- `memory_embeddings` table (vector similarity)
- Importance score
- Temporal factors

The `metadata_json` field is a storage field, not a search field. Enriched title/keywords do not improve search results — they are dead data. The pipeline also adds 4+ minutes of latency when the LLM API key is missing (timeout behavior).

## Impact

- Enrichment effort is wasted — no searchability improvement
- Users cannot search by enriched title/keywords
- Pipeline adds latency without delivering value
- Default enrichment mode must be disabled (DEC-0047)

## Scope Note (2026-08-20, DEC-0059)

The "basically useless for improving search quality" claim applies to **Mnemosyne
retrieval only**. The **bensyne-mcp file layer** does consume enriched metadata: the
whole-file LLM summary is persisted (`files.summary`) and surfaced on recall as
`summary_chain` / `related_files[].summary`, and title/keywords appear in recall read
enrichment (DEC-0059). Enrichment is live in dev (`enrichment.enabled: true`). The
Mnemosyne-side gap (metadata_json not indexed for search) remains as described above.
