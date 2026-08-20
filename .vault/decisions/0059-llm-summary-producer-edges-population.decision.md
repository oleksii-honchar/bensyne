---
type: decision
id: DEC-0059
system: shared
title: "LLM Whole-File Summary Producer + Edges Population"
status: accepted
createdAt: "2026-08-20T13:49:01Z"
updatedAt: "2026-08-20T13:49:01Z"
tags: [enrichment, summarisation, edges, racochu, bensyne-mcp, file-layer]
supersedes: []
superseded_by: []
see_also: [
  "decisions/0021-selective-summarization-strategy.decision.md",
  "decisions/0046-document-level-graph-metadata.decision.md",
  "decisions/0047-disable-enrichment-by-default.decision.md",
  "specifications/0004-enrichment-pipeline.spec.md",
  "concepts/0021-llm-enrichment.concept.md",
  "concepts/0007-file-metadata-layer.concept.md"
]
---

# DEC-0059: LLM Whole-File Summary Producer + Edges Population

## Context

The summary axis was designed (DEC-0021 proposed; SPEC-0002 Phase 3; cornerstone
"summarized relationship of connected nodes") and its consumer side fully built (wire
`summary`, `files.summary` column, `summary_chain`, `related_files[].summary`,
`summary_only`) — but the producer side was never implemented: the racochu DTO hardcoded
`summary: null`, the live LLM enrichment requested only `{title, keywords}`, and
`docMaxTokens` was dead config. Every recall fell back to the mechanical
`"File: {path}. Keywords: …"` string. Edge `description` was persisted
(`file_relations.description`) but dropped on every read path.

## Decision

Three parts (code-verified 2026-08-20):

1. **Producer: LLM whole-file summary in the existing enrichment call (racochu).**
   Enrichment schema extended `{title, keywords}` → `{title, keywords, summary}`; Mastra
   stamps `metadata.mastraDocSummary` on every chunk (DEC-0046 document-level pattern); the
   DTO maps it to the wire `summary` field (replaces the hardcoded `null` at
   `bensyne-remember.dto.ts:108` → `metadata.mastraDocSummary ?? null`); `mastraDocSummary`
   added to the consumed-key skip list. `docMaxTokens` became live as the summary word-cap
   guard: `summaryMaxWords = clamp(floor(docMaxTokens/200), 20, 120)` (default 16000 → 80
   words). Order-independent convergence verified: `File.update_metadata` preserves summary
   on `None`. No rule-based producer stage (user directive says LLM); the read-side
   mechanical fallback remains the degraded path (DEC-0021 rule-based-first clause
   superseded).

2. **Edges population: every relation carries the whole-file summary + its description
   (bensyne-mcp, additive-only).** Surface on every relation/edge read path: the relation's
   own `description` (already persisted) and the target file's whole-file `summary`:
   - recall/searchFiles enrichment `relations[]`: + `description`
   - recall/searchFiles enrichment `related_files[]`: + `description`
   - searchFiles `related_files[]`: + `summary` + `description`
   - expandFileRelations expanded entries: + `description` (use-case level, both paths)
   No aggregate/entity/schema changes; `File.to_dict()` canonical block untouched; zero
   migrations.

3. **Vault reconciliation (this node + DEC-0021 flip, SPEC-0002, concept 0021, DEC-0047
   note).**

## Alternatives Considered

- *Rule-based producer stage (DEC-0021 "rule-based first")* — rejected: user directive is
  explicitly LLM summarisation; mechanical read fallback covers the no-LLM path
- *Separate dedicated summarisation LLM call* — rejected: doubles LLM cost; enrichment call
  already runs per document
- *Store summary only on the first chunk* — rejected: order-fragile; stamping every chunk is
  uniform and idempotent (DEC-0046 pattern)
- *Add summary to `File.to_dict()` canonical 10-key block* — rejected: ripples to 4 call
  sites + shape-pin tests; summary already surfaced via `summary_chain` +
  `related_files[].summary`
- *Per-section summaries* — out of scope: no consumer path exists
- *Omit `summary` key when absent* — rejected: keep always-present `null` per contract
- *Leave parity fixture untouched* — rejected: extending the fixture (H7) locks the new
  mapping via byte-identical re-pin

## Consequences

- `File.summary` becomes live: `summary_chain` heads with a real LLM whole-file summary;
  `related_files[].summary` and `expandFileRelations summary_only` stop being dead paths
- Every retrieved relation carries the connected node's whole-file summary + the relation's
  description — the cornerstone's "summarized relationship of connected nodes"
- LLM enrichment gains one field per existing call; `docMaxTokens` finally governs summary
  length; failure is non-fatal (DEC-0043)
- No `contract_version` bump (`summary: string | null` already declared in v1); no
  schema/migration; D41/D39/D40/D42/D43 unaffected; `File.to_dict()` canonical block unchanged
- Parity fixture re-pinned (H7, byte-identical both copies; old sha → 0 matches gate)
- Verified in code: `bensyne-remember.dto.ts:109` maps `mastraDocSummary`; `dev.yaml`
  `enrichment.enabled: true`
