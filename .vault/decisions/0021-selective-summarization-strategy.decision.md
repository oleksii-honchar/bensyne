---
type: decision
id: DEC-0021
system: racochu
title: "Selective Summarization Strategy"
status: accepted
createdAt: "2026-07-30T23:00:00Z"
updatedAt: "2026-08-20T13:49:01Z"
tags: [enhancement, chunking]
supersedes: []
superseded_by: []
see_also: ["decisions/0059-llm-summary-producer-edges-population.decision.md"]
---

# DEC-0021: Selective Summarization Strategy

## Context

Need to summarize content that exceeds character limits, but only for appropriate content types.

## Decision

Implement selective summarization only for prose and documentation content, using rule-based algorithms first, with optional LLM enhancement (via `enrichmentConfig` in config-schemas.ts).

## Alternatives Considered

1. **Always summarize** — Summarize all content types
2. **Never summarize** — Only truncate content
3. **Always use LLM** — Always use AI for summarization

## Consequences

- **Positive**: Better content quality, reliable fallback without external dependencies
- **Negative**: More complex implementation (not yet implemented — proposed for future)

## Reconciliation Note (2026-08-20, DEC-0059)

**Status flip: proposed → accepted.** Implemented via this decision's named vehicle,
`enrichmentConfig`, in the existing per-document LLM enrichment call (racochu →
bensyne-mcp). The **"rule-based algorithms first" clause is superseded** — user directive
(2026-08-19/20) requires LLM summarisation; the read-side mechanical fallback remains the
degraded no-LLM path. Whole-file summary (80-word cap by default, `summaryMaxWords =
clamp(floor(docMaxTokens/200), 20, 120)`) is stamped as `mastraDocSummary` on every chunk and
surfaced by the bensyne-mcp file layer via `summary_chain` / `related_files[].summary`.
See [[0059-llm-summary-producer-edges-population]].
