---
type: adr
id: ADR-0003
title: "Selective Summarization Strategy"
status: proposed
createdAt: "2026-07-30T23:00:00Z"
updatedAt: "2026-07-31T07:30:00Z"
tags: [enhancement, chunking]
see_also: []
---

# ADR-0003: Selective Summarization Strategy

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
