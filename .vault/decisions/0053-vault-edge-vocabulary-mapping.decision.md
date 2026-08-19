---
type: decision
id: DEC-0053
system: racochu
title: "Vault Edge Vocabulary Mapping — see_also as recommendation, wikilinks as backlink"
status: accepted
createdAt: "2026-08-19T18:44:41Z"
updatedAt: "2026-08-19T18:44:41Z"
tags: [chunking, vault, edges, graph, relation-types]
supersedes: []
superseded_by: []
see_also: [decisions/0045-wikilink-extraction-graph-structure.decision.md, decisions/0049-agent-session-cross-reference-edges.decision.md, concepts/0006-file-chunk-relation.concept.md]
---

# DEC-0053: Vault Edge Vocabulary Mapping

## Context

The 9-value relation vocabulary is 1:1 locked TS↔PY; only the semantic mapping of vault
edge mechanisms was open. Precedents: obsidian wikilinks = `backlink`/1.0 (DEC-0045 era);
the 0.7 strength exists only for *heuristic* content refs (DEC-0049).

## Decision

| Mechanism | `relation_type` | `strength` | Rationale |
|-----------|-----------------|-----------|-----------|
| `see_also` frontmatter | `recommendation` | 1.0 | Deliberate, curated author pointers; deterministic, not heuristic → full strength |
| Body wikilinks `[[...]]` | `backlink` | 1.0 | Exact obsidian precedent; author links are explicit |

## Alternatives Considered

| Alternative | Why rejected |
|-------------|--------------|
| `see_also` → `cross_reference` (0.7) | `cross_reference` is the agent-session content-ref type; 0.7 understates explicit frontmatter curation |
| `see_also` → `dependency` / `sibling` | Wrong semantics: see_also is "related reading", not structural coupling or folder kinship |
| `version`/`override` for supersedes/superseded_by | Fits semantically, but out of the scoped edge mechanisms; **deferred** (metadata-only for now) |

## Consequences

- **Positive:** Semantically honest edges; recall can distinguish curated links from inline mentions.
- **Neutral:** No vocabulary changes — the TS↔PY lock is preserved.
- **Accepted quirk:** "backlink" is slightly misleading for forward links; consistency with the
  obsidian precedent wins over naming purity.
