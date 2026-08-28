---
type: decision
id: DEC-0095
title: "Bank Discovery Search Tool — searchMemoryBank as Sibling of listMemoryBanks"
status: accepted
createdAt: "2026-08-28T12:58:00Z"
updatedAt: "2026-08-28T12:58:00Z"
system: bensyne-mcp
tags: [mcp, bank-discovery, tool-surface, backward-compat]
supersedes: []
superseded_by: []
see_also:
  - concepts/0026-bank-discovery-search-vs-list.concept.md
  - memories/0024-mcp-tool-description-is-canonical-teaching-surface.memory.md
  - decisions/0095-channel-weighted-keyword-ranking.decision.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# DEC-0095: Bank Discovery Search Tool — searchMemoryBank as Sibling of listMemoryBanks

## Context

The Bensyne MCP exposes 12 tools; `listMemoryBanks` returns every bank
in the namespace. With the persona ecosystem scaling (15 live banks in
the current environment: 11 `persona_*`, 2 user-profile, 2 source-type;
grows with each new agent type), every agent is forced to enumerate
all banks before choosing. The canonical Bensyne skill (`skills/bensyne/SKILL.md`)
mandated `listMemoryBanks` as the entry point in six places, and a
literal test assertion (`test_mcp_tool_descriptions.py`) cemented the
"ALWAYS run first" nudge.

Operators, racochu reconcile, and observability scripts depend on the
`listMemoryBanks` wire shape (`{banks: [...]}`); a breaking change is
out of scope.

## Decision

Add `searchMemoryBank` as a **sibling** MCP tool to `listMemoryBanks`.
The two coexist:

- `listMemoryBanks` — diagnostic / full enumeration. Description
  reframed from "ALWAYS first" to "diagnostics, full enumeration, or
  when searchMemoryBank returns no useful matches." Wire shape
  unchanged.
- `searchMemoryBank` — canonical discovery primitive. Free-text
  `query` matched against bank `name`, `description`, and derived
  keywords. Returns ranked `{matches, total}`.

`searchMemoryBank` signature: `searchMemoryBank(query: str, limit: int = 10, agent_id: str | None = None) -> dict`.

Tool description (the canonical teaching surface per
`memories/0024-mcp-tool-description-is-canonical-teaching-surface`) is
authored to say **"Prefer this over listMemoryBanks for scoped
discovery"** — agents that load Bensyne without loading the skill
still learn the new primitive.

The four `_MEMORY_BANK_*_DESC` parameter-description constants in
`app.py` (lines 30–54) are softened from
`"Run listMemoryBanks first to confirm which banks exist."` to
`"Use searchMemoryBank (preferred) or listMemoryBanks (diagnostic) to
confirm which banks exist."` — propagates the corrected nudge to every
per-tool parameter description without per-tool edits.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|---------------|
| **A. Replace `listMemoryBanks` with `searchMemoryBank`** | Smaller surface | Breaks operators / observability / racochu reconcile; forces every caller to pass a query | Backward-compat cost too high |
| **B. Add optional `filter` to `listMemoryBanks`** | One tool | Pollutes diagnostic tool with discovery semantics; callers still get unfiltered payload by default | Bad tool boundaries |
| **C. Skill text edit only, no new tool** | No new code | Skills can drift; schema is authoritative teaching surface for agents that never load the skill | Wrong place to encode the rule |

## Consequences

- **Positive:** Operators / observability keep working; agents get a
  ranked discovery primitive; nudge is encoded in the tool description
  (not just the skill).
- **Positive:** Tool count 14 → 15; `EXPECTED_TOOLS` in
  `test_mcp_tool_descriptions.py` updates 14 → 15.
- **Positive:** `_MEMORY_BANK_*_DESC` softening is a single propagation
  point for the corrected nudge.
- **Negative:** Two description tests change; one new test added
  (`test_search_memory_bank_encodes_prefer`).
- **Neutral:** `mock_mcp.tool.call_count >= 6` bumps to `>= 7` in
  `test_app.py`.