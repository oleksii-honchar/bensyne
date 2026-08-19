---
type: decision
id: DEC-0051
system: racochu
title: "Dedicated Vault Chunking Strategy"
status: accepted
createdAt: "2026-08-19T18:44:41Z"
updatedAt: "2026-08-19T18:44:41Z"
tags: [chunking, vault, strategy, racochu]
supersedes: []
superseded_by: []
see_also: [decisions/0034-custom-chunking-strategies-framework.decision.md, decisions/0048-dual-hash-wire-contract.decision.md, concepts/0024-vault-note-chunking.concept.md, decisions/0054-vault-wikilink-resolution-ladder.decision.md]
---

# DEC-0051: Dedicated Vault Chunking Strategy

## Context

`sourceType: vault` (the racochu default, per [[0048-dual-hash-wire-contract]]) fell through
to the generic MastraChunkingService. Vault grammar (index/MOC files, node taxonomy,
`see_also` frontmatter, body wikilinks) had no consumer — vault sources ingested as generic
Markdown with their structure lost.

## Decision

New `VaultChunkingStrategy` class in `apps/racochu/src/application/strategies/`, registered in
`StrategyRouter` (`[SOURCE_TYPES.VAULT] → vaultStrategy`) and `app.module.ts` providers —
follows the [[0034-custom-chunking-strategies-framework]] pattern exactly (class + router
case + DI provider). Body chunking delegates to the existing `MastraChunkingService`.

Verified in code:
- `vault-chunking.strategy.ts` — `VaultChunkingStrategy` class
- `strategy-router.service.ts` — `[SOURCE_TYPES.VAULT]: this.vaultStrategy`
- `watch-source.entity.ts` — `sourceType` defaults to `SOURCE_TYPES.VAULT`

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| Enhance MastraChunkingService (content-aware) | Minimal code | Pollutes generic chunking | DEC-0034 explicitly rejected this |
| Extend ObsidianChunkingStrategy with a vault mode | Reuses wikilink code | Different resolution semantics + edge contract | One class, two behaviors = the coupling DEC-0034 avoided |

## Consequences

- **Positive:** Additive, zero impact on other source types; vault structure (edges, index skip,
  metadata) becomes first-class.
- **Negative:** Third strategy class; per-class test coverage required.
