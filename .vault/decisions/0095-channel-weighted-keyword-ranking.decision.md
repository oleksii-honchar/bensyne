---
type: decision
id: DEC-0096
title: "Channel-Weighted Keyword Ranking — v1 Substring/Token Scoring Without Embeddings"
status: accepted
createdAt: "2026-08-28T12:58:00Z"
updatedAt: "2026-08-28T12:58:00Z"
system: bensyne-mcp
tags: [mcp, scoring, ranking, bank-discovery]
supersedes: []
superseded_by: []
see_also:
  - decisions/0094-bank-discovery-search-tool.decision.md
  - decisions/0096-bank-description-backfill-via-operator-script.decision.md
  - memories/0025-channel-weighting-makes-description-backfill-load-bearing.memory.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# DEC-0096: Channel-Weighted Keyword Ranking — v1 Substring/Token Scoring Without Embeddings

## Context

11 persona banks all share near-identical descriptions
(`"<role> agent decision tree (persona)"`); 2 source banks (`agent-sessions`,
`vault`) carry empty descriptions in the production registry today.
Description-only substring match would not discriminate between persona
banks; an empty-description bank would systematically under-rank.

The v1 search tool needs a ranking algorithm that is:

- Cheap (single-digit-ms per call; O(N×T) substring match).
- Backward-compatible (no `registerMemoryBank` schema change).
- Robust to empty descriptions.
- Incentivising bank owners to maintain descriptions.

## Decision

v1 uses **pure-derived keywords from the bank name** plus
**channel-weighted substring scoring** — no embeddings, no schema
change.

```python
CHANNEL_WEIGHTS = {"name": 1, "description": 2, "derived": 1}
PERSONA_MATCH_BONUS = 2  # applied when name == f"persona_{agent_id}"
DEFAULT_LIMIT, MIN_LIMIT, MAX_LIMIT = 10, 1, 50
```

Scoring:

```
score = 0
for term in query_terms:
    if term in name.lower():                score += 1
    if term in (description or "").lower(): score += 2   # ADR-S12
    if term in _derived_keywords_for(name): score += 1
if agent_id and name == f"persona_{agent_id}": score += 2
```

Sort by `(-score, name)`; truncate to `limit`; drop zero-score
entries.

**Channel weighting rationale (ADR-S12):**

- `description` is human-curated via `registerMemoryBank(...)` —
  highest-trust signal. Weight **+2**.
- `name` is often a role slug (`persona_<x>`, `agent-sessions`,
  `vault`) — a system identifier, not a vocabulary surface. Weight
  **+1**.
- `derived` keywords are auto-computed from `name` (split on
  non-alphanumeric, lowercase, dedupe). Weight **+1**.

The `+2` persona-match bonus is small relative to a multi-channel hit
(up to `4 × |terms| + 2`); it acts as a tiebreaker, not a dominant
signal.

**Derivation (post-ship deviation, see ADR-S13 follow-up):** The
original spec (`spec.md` C2, `decisions.md` ADR-S2) defined a
`PER_ROLE_KEYWORDS: dict[str, list[str]]` constant (~15 entries)
giving each persona a hand-curated vocabulary. After the implementation
landed, a refactor pass at user direction ("no hardcoded stuff")
**dropped `PER_ROLE_KEYWORDS` and the `user_<id>` special case**.
`_derived_keywords_for(name)` is now pure tokenisation. The
skill-text per-agent starter-keyword table still embeds the
hand-curated vocabulary (e.g. `researcher → "investigation findings
hypothesis evidence"`), but only terms that substring-match the
bank name or description will score — the table is currently
**advisory only**, not algorithmically effective. Follow-up ADR-S13
needs to reconcile this (either restore `PER_ROLE_KEYWORDS`, or trim
the skill-text vocabulary to words the algorithm scores on).

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|---------------|
| **A. Extend `registerMemoryBank` with `keywords: list[str]`** | Bank-owner control; decouples from naming convention | Schema change + write discipline change + backfill every existing bank; field unused by v1 scoring | Deferred until demand (~25 banks or naming drift) |
| **B. Probe recall per bank, rank by overlap** | Most relevant ranking | O(N) Mnemosyne calls per search; turns 1ms lookup into 200ms+ cascade | Deferred to when bank count > 30 or description-only is too noisy |
| **C. Hybrid (derived + top-K probe)** | Best of both | Introduces Mnemosyne latency dependency v1 tool should not have | Deferred |
| **D. Uniform `+1` per channel** | Simpler | Under-credits curated descriptions; the empty-description problem becomes invisible until backfill fails; noisier rankings because the only difference between banks is the implicit vocabulary in their names | Rejected by ADR-S12 |
| **E. Higher description weight (`+3`)** | Incentivises descriptions | Swamps the `+2` persona bonus; biases toward project banks over persona banks | `+2` is the largest weight that keeps the bonus competitive |

## Consequences

- **Positive:** Algorithm depends only on data `listMemoryBanks`
  already returns — no schema change, no new aggregate, no write
  discipline.
- **Positive:** `description` weight `+2` makes the
  `backfill-bank-descriptions.sh` script (DEC-0097) load-bearing —
  agents learn that maintaining descriptions matters.
- **Positive:** Pure-derived keywords mean new `persona_*` banks work
  for free; no maintenance gap between a new bank appearing and its
  vocabulary being added.
- **Negative:** Skill-text per-agent table vocabulary is currently
  advisory only — see ADR-S13 follow-up. Recommend trimming the
  table to words the algorithm scores on (name tokens + description
  vocabulary).
- **Neutral:** Scoring lives in `SearchMemoryBankUseCase.execute_internal`
  (single file knows the rules; per `04-patterns.mdc`, scoring does
  not span aggregates — no domain service warranted).
- **Neutral:** Future ADR can add `keywords: list[str]` to
  `registerMemoryBank` additively without breaking v1.