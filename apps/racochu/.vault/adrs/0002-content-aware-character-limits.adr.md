---
type: adr
id: ADR-0002
title: "Content-Aware Character Limits"
status: accepted
createdAt: "2026-07-30T23:00:00Z"
updatedAt: "2026-07-31T07:30:00Z"
tags: [enhancement, chunking]
see_also: ["concepts/0006-mastra-chunking-strategies.concept.md"]
---

# ADR-0002: Content-Aware Character Limits

## Context

Need to enforce character count limits that respect different content types.

## Decision

Implement content-aware character limits via enhancement config (`enhancement.maxCharacters`) passed to Mastra chunking strategies natively:

| Content Type | Max Chars | Config Key |
|--------------|-----------|------------|
| Prose | 200 | `prose` |
| Code | 400 | `code` |
| Configuration | 300 | `configuration` |
| Documentation | 300 | `documentation` |

Verified in `MastraChunkingService.getMaxCharacters()` and applied via `applyChunking()` method options.

## Alternatives Considered

1. **Fixed limits** — Same character limit for all content
2. **Token-based approach** — Use token count instead of characters
3. **LLM-based summarization** — Always use AI for summarization

## Consequences

- **Positive**: Better content quality, appropriate processing per type
- **Negative**: More complex configuration
- **Mitigation**: Defaults provided in `enhancementConfigSchema` (config-schemas.ts)
