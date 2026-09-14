---
type: decision
id: DEC-0109
system: shared
title: "ADR-12: Per-Session Memory Banks with Traversal History"
status: accepted
createdAt: "2026-09-14T16:36:00Z"
updatedAt: "2026-09-14T16:36:00Z"
tags: [session-memory, traversal-history, bank-naming, post-compaction-recall, agent-personas]
supersedes: []
superseded_by: []
see_also:
  - concepts/0027-bank-naming-contract.concept.md
  - memories/0020-mnemosyne-valid-until-soft-expiry.memory.md
  - specifications/0006-source-ttl-sweep.spec.md
---

# ADR-12: Per-Session Memory Banks with Traversal History

## Context

Agents lose their decision-tree position when the session context is compacted:
traversal position was explicitly "in-session only", all sessions for a user
shared the `agent-sessions_{user_id}` bank (mixing histories and making
per-session recall noisy), and the 2-memory-per-task write budget prevented
per-node traversal tracking. After compaction, the agent had to re-traverse
from the persona entry node.

## Decision

Introduce a per-session memory bank for each agent session:

- **Bank naming:** `agent-session-{session_id}` (hyphen, singular) —
  distinct from the user-suffixed `agent-sessions_{user_id}` (underscore,
  plural) and from the DEC-0102 floor-score prefixes (`user_` /
  `agent-sessions_`).
- **Implicit creation:** banks are not pre-registered; they are created on
  first write via the existing Bensyne bank auto-registration mechanism.
- **Traversal history category:** agents write a structured memory after each
  decision-tree node transition:
  `{"category":"traversal-history","node_id":"...","edge_when":"...","accepted":true,"occurred_at":"...","node_enter_context":"..."}`
- **Write-budget exemption:** `traversal-history` memories are structural and
  low-cost; they are **exempt** from the 2-memory-per-task limit.
- **Post-compaction recall (better-opencode fork):** after compaction, the
  agent recalls the session bank to reconstruct its decision position.
  Implemented via the existing `experimental.compaction.post_recall` hook
  (fork commits on `patched/dev2`, e.g. `b8d5c6aa0`).

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| `agent-session_{session_id}` (underscore) | No hyphen/underscore ambiguity | Collides visually with `agent-sessions_{user_id}`; weaker prefix signal | Hyphen chosen for clear separation |
| `session-{session_id}` | Shorter | No agent/namespace context; collision risk with other `session-*` names | Need explicit per-agent namespace |
| `agent-sessions/{session_id}` (path-style) | Hierarchical | Requires path parsing; breaks flat bank name contract | Banks are flat namespaces |
| Flat text traversal memories | Simple | Brittle reconstruction; no metadata filtering | Structured metadata enables precise recall |
| Raise global write budget to 10-20 | Simple | Allows over-writing user profile / occasional memories | Category-scoped exemption is safer |
| Direct better-opencode→Bensyne coupling | Fewer moving parts | Tight coupling; fork owns Bensyne-specific code | Plugin hook keeps fork generic |

## Consequences

- **Positive:** agents reconstruct their decision position after compaction;
  session histories are isolated; per-move writes are cheap and exempt from
  the user-memory budget; Bensyne MCP tools unchanged (banks are just
  differently-named existing namespaces).
- **Negative:** session banks accumulate over time — periodic pruning of
  empty/stale banks may be needed; per-session banks are not Racochu-watched
  (agent-writable only), so they live outside the source-ingestion lifecycle.
- **Neutral:** `valid_until` remains accepted-but-dropped on write (see
  [[memories/0020-mnemosyne-valid-until-soft-expiry]]); traversal history is
  intentionally excluded from the user profile bank.

## Notes

Decisions 1-6 from session `ses_f614d802bffeWF4Qx5n3x4A0TU` (bank naming,
post-compaction hook, traversal category, write-budget exemption, session
isolation, fork plugin approach) are consolidated here. The skills
(`skills/bensyne/SKILL.md`, `skills/agent-persona-base/SKILL.md`) and this
vault node are the canonical teaching surfaces; the concept contract in
[[concepts/0027-bank-naming-contract]] is the naming source of truth.

⚠️ **Unverified (as of 2026-09-14):** the Bensyne recall plugin is in
development in the better-opencode fork at
`packages/opencode/src/plugin/bensyne/` (uncommitted modifications); the
`.opencode/plugins/bensyne-recall.ts` path referenced in session specs was
not found. End-to-end verification (compaction → recall → reconstruction)
is still pending in the implementation plan (Phases 3-4).