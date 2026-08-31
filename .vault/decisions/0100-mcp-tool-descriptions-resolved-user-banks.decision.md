---
type: decision
id: DEC-0101
title: "MCP Tool Descriptions Teach the Resolved User-Suffixed Banks"
status: accepted
createdAt: "2026-08-31T12:40:34Z"
updatedAt: "2026-08-31T12:40:34Z"
system: bensyne-mcp
tags: [mcp, bank-discovery, agent-nudge, tool-descriptions]
supersedes: []
superseded_by: []
see_also:
  - decisions/0094-bank-discovery-search-tool.decision.md
  - decisions/0101-search-memory-bank-user-suffixed-inclusion.decision.md
  - concepts/0027-bank-naming-contract.concept.md
  - memories/0024-mcp-tool-description-is-canonical-teaching-surface.memory.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# DEC-0101: MCP Tool Descriptions Teach the Resolved User-Suffixed Banks

## Context

On 2026-08-31 the architect sub-agent (session
260831-1151-simple-session-materials, ses_fa8bcba7cffem1vd6FKCpoHjYC)
recalled user memories from the `default` bank and prior context from the
bare `agent-sessions` bank — both empty legacy shells deleted 2026-08-29.
All recalls returned `results: []`; the agent worked with zero memory
awareness.

Root cause (verified from opencode.db, see session
260831-1207-bensyne-personas-analysis-refinement E1–E3): the runtime
tool-catalog descriptions authored in `apps/bensyne-mcp/src/app.py`
named `default` "the user profile bank" and `agent-sessions` the
prior-context bank ("At task start, recall 'agent-sessions' and
'default' first to build awareness"). The architect issued recalls in
the same turn as skill loading — bank choice came from the short,
salient tool description before the longer skill text (bensyne Phase 1
bank resolution) could be absorbed. The skills said the right thing;
the tools said the wrong thing — and the tools win.

## Decision

Rewrite the `_MEMORY_BANK_WRITE_DESC` / `_MEMORY_BANK_READ_DESC`
constants and the 8 tool docstrings in `apps/bensyne-mcp/src/app.py`
(plus `MEMORY_BANK_PARAM` in `src/infrastructure/mcp/schemas.py`) to
teach the resolved bank contract:

- User profile: `user_<id>` (resolved from `~/.config/racochu.yaml`:
  `user.bank` else `user_<id>`).
- Prior context: `agent-sessions_{user_id}` (user id as suffix).
- `default` / `agent-sessions` explicitly marked "legacy shells
  (deleted 2026-08-29) — do not use them".
- "Empty bank = no context yet" note added to `getMemoryStats` and
  `listMemoryBanks` descriptions so empty results are never treated
  as authoritative.

Companion edits (same change): `~/.rules/olho/always-apply/
bensyne-memory.mdc` renamed "user-profile (default) bank" →
"user-profile (`user_<id>`) bank"; `skills/bensyne/SKILL.md` gained
the empty-bank note and a recall-first grounding note.

Implementation: committed (working tree clean for the fix; version
bumped 1.1.4 → 1.2.0 in `pyproject.toml` + `package.json`). Tests
`test_mcp_tool_descriptions.py` (17/17) and `test_skills/` (9/9)
pass with the new assertions.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|---------------|
| **A. Skill text edit only** | Simple | Skills may not be loaded; skill text can drift from schema | Schema is the authoritative teaching surface (memories/0024); wrong wording would persist for skill-less agents |
| **B. Always-apply rule edit only** | Reaches every agent | Rule layer should not duplicate tool guidance; descriptions would still teach wrong banks | Wrong layer; the catalog description is read at task start by every agent regardless of rules |
| **C. Leave as-is, rely on skills** | No change | Demonstrated to fail: same-turn recall beats skill absorption | The 2026-08-31 incident is the counter-example |

## Consequences

- **Positive:** Every agent sees the correct bank contract at task
  start via the MCP schema — with or without the skill loaded.
- **Positive:** The "empty bank = no context yet" note removes a
  silent failure mode (empty legacy recall read as "nothing exists").
- **Negative:** Description test assertions must track the schema
  wording (gated by `test_mcp_tool_descriptions.py`).
- **Negative (deployment):** Code fix does not take effect until the
  live server is restarted with the new image — the runtime catalog
  kept teaching legacy banks after the code fix (observed 2026-08-31).
- **Neutral:** `listMemoryBanks` needed no code change — it already
  enumerates every bank; only its description taught legacy banks.
