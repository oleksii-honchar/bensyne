---
type: decision
id: DEC-0098
title: "Bank Discovery Skill Nudge — Centralised Edit + Inline Per-Agent Starter Keywords"
status: accepted
createdAt: "2026-08-28T12:58:00Z"
updatedAt: "2026-08-28T12:58:00Z"
system: shared
tags: [skills, agent-personas, bank-discovery, centralised]
supersedes: []
superseded_by: []
see_also:
  - decisions/0094-bank-discovery-search-tool.decision.md
  - concepts/0026-bank-discovery-search-vs-list.concept.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# DEC-0098: Bank Discovery Skill Nudge — Centralised Edit + Inline Per-Agent Starter Keywords

## Context

`listMemoryBanks` was referenced in exactly **three** skill files:

- `skills/bensyne/SKILL.md` — 6 references (the canonical memory skill;
  loaded by every agent that uses Bensyne).
- `skills/agent-persona-base/SKILL.md` — 1 reference (STOP rule).
- `skills/agent-persona-coach/SKILL.md` — 2 references.

Per-agent wrappers (11 of them under `agents/bensyne-personas/*.md`)
carried **zero** references. A single canonical edit to the Bensyne
skill propagates to every agent; two minor companion edits cover the
persona skills.

## Decision

Edit the **canonical** `skills/bensyne/SKILL.md` in seven places
(introduction continuation check, Phase 1 step 2/3, Phase 2 vault
recall, reference list addendum, Success Criteria, Quality Checklist)
and append an 11-row **per-agent starter-keyword table** inline
after Phase 1 step 5:

| Agent | Starter query |
|---|---|
| `architect` | `specification decision architecture ADR` |
| `developer` | `code implementation plan test` |
| `generalist` | *(derive from user request)* |
| `icm-operator` | `incident postmortem runbook monitoring` |
| `researcher` | `investigation findings hypothesis evidence` |
| `reviewer` | `review acceptance criteria correctness` |
| `session` | `session dispatch routing agent` |
| `super-developer` | `code implementation plan test` |
| `super-worker` | `codebase test implementation` |
| `vault-keeper` | `vault knowledge promote ADR` |
| `worker` | `codebase test implementation` |

`generalist` has no fixed starter keywords — its tasks span every
domain. The skill text says: "extract 2–3 task-relevant terms (nouns
and verbs the request names) and pass them to `searchMemoryBank`."

The table is **inline** in the skill text, not a separate file —
single source of truth, no extra file to maintain, ~11 rows fits
inline without ceremony.

Companion edits:

- `skills/agent-persona-base/SKILL.md` (STOP rule) — relax the
  condition: "If the bank does not surface in `searchMemoryBank` (or
  `listMemoryBanks`) or `node_memories` is 0, do not proceed without
  your decision tree."
- `skills/agent-persona-coach/SKILL.md` (2 places) — language tweaks
  to align with the search-first flow.

**Drift gates:** `tests/test_skills/test_skill_text_drift.py` greps
every `*.md` file under `skills/` for the substring
`listMemoryBanks first` and asserts 0 matches (catches regression).

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|---------------|
| **A. Edit per-agent wrappers individually** | Targeted | Zero current references; risk of inconsistent nudges across agents | Wrong blast radius |
| **B. Always-apply rule update (`bensyne-memory.mdc`)** | Reaches every agent | The rule does NOT name `listMemoryBanks`; stays clean and tool-agnostic | Premature |
| **C. New skill file `skills/bensyne/bank-discovery.md`** | Isolates the change | Fragments guidance from the canonical skill; new file to keep in sync | Convention says canonical is the carrier |
| **D. New rule `~/.rules/olho/always-apply/bensyne-bank-search.mdc`** | Reaches every agent | Rule layer should not duplicate skill guidance | Wrong layer |

## Consequences

- **Positive:** 7 edits + 1 inline table in one canonical file
  propagate to every agent that loads Bensyne.
- **Positive:** Drift gate catches future regressions where
  `listMemoryBanks first` reappears.
- **Negative:** Per-agent starter-keyword table vocabulary is
  currently advisory only — only words that substring-match a bank's
  name or description will score under pure-derived keyword ranking.
  See DEC-0096 Consequences / ADR-S13 follow-up. Recommended action:
  trim the table vocabulary to words the algorithm scores on.
- **Neutral:** No edits to any of the 11 per-agent wrapper files.
- **Neutral:** Future ADR can move the table to a dedicated file
  (`skills/bensyne/agent-keywords.md`) once it grows past ~20 rows.