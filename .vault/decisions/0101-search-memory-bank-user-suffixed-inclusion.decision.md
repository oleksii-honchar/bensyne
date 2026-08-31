---
type: decision
id: DEC-0102
title: "searchMemoryBank Always Surfaces User-Suffixed Banks (Floor Score 1)"
status: accepted
createdAt: "2026-08-31T12:40:34Z"
updatedAt: "2026-08-31T12:40:34Z"
system: bensyne-mcp
tags: [mcp, scoring, ranking, bank-discovery]
supersedes: []
superseded_by: []
see_also:
  - decisions/0095-channel-weighted-keyword-ranking.decision.md
  - decisions/0100-mcp-tool-descriptions-resolved-user-banks.decision.md
  - concepts/0027-bank-naming-contract.concept.md
  - memories/0025-channel-weighting-makes-description-backfill-load-bearing.memory.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# DEC-0102: searchMemoryBank Always Surfaces User-Suffixed Banks (Floor Score 1)

## Context

`searchMemoryBank` (DEC-0096) uses channel-weighted lexical substring
scoring and drops score-0 banks. The user/session bank vocabularies
(`user`, `<id>`, `session`, `history`) never match task-shaped
queries ("architecture", "specification", "ADR"), so
`user_oleksii` / `agent-sessions_oleksii` score 0 and are dropped —
invisible to discovery. In the 2026-08-31 incident the architect's
only `searchMemoryBank` call returned 11 `agent-persona_*` banks and
none of the user banks (evidence E7: pure lexical scoring + zero-drop,
no policy exclusion).

The zero-score drop was intentional noise control; hiding the
*most* task-relevant banks (user profile + prior-session context)
is an unintended consequence.

## Decision

In `SearchMemoryBankUseCase`
(`apps/bensyne-mcp/src/application/use_cases/
search_memory_bank_use_case.py`): add
`USER_SUFFIXED_PREFIXES = ("user_", "agent-sessions_")`. A bank whose
name starts with a user-suffixed prefix and whose lexical score is 0
gets a **floor score of 1** and is always included in results. The
zero-score drop, channel weights, persona bonus, `(-score, name)`
sort, and `limit` truncation are otherwise unchanged.

Floor = 1 (not 0) so user banks interleave with weak lexical matches
and stay visible in the default `limit=10` window, without distorting
the relative ranking of positively scored banks.

Implementation: committed; `TestUserSuffixedBankInclusion`
(4/4), `test_search_memory_bank_use_case.py` (31/31), e2e
`test_search_memory_banks.py` (5/5) pass.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|---------------|
| **A. Append user-bank keywords to the query** | No scoring change | Server cannot know the user id without config access; query is agent-authored | The bank-name prefix is the reliable signal |
| **B. Remove the zero-score drop entirely** | All banks always visible | Floods results with irrelevant banks; defeats DEC-0096's noise control | Over-broad blast radius |
| **C. Backfill user-bank descriptions with task vocabulary** | Works within existing scoring | Fragile per-user curation; vocabulary drifts from real task queries | Maintenance burden for a system-level guarantee |
| **D. Floor score 0 (include, sort last)** | Minimal interference | Sorts strictly last; `limit=10` cuts them when personas score higher | Defeats the visibility goal |

## Consequences

- **Positive:** Discovery surfaces the real user profile and
  prior-session context for task-shaped queries — the recall-first
  contract now works end-to-end.
- **Positive:** ADR-S12 scoring is preserved — this is a targeted
  exception for a known bank family, not a reversal of the algorithm.
- **Negative:** `searchMemoryBank` results change for queries that
  previously returned only persona banks (intended; e2e
  `test_empty_result_for_nonsense_query` reconciled accordingly).
- **Neutral:** New user-suffixed banks appear in search results
  automatically via the name prefix — no curation required.
