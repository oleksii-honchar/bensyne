---
type: concept
title: "Bank Discovery — Search vs List"
createdAt: "2026-08-28T12:58:00Z"
updatedAt: "2026-08-28T12:58:00Z"
system: bensyne-mcp
tags: [mcp, bank-discovery, tool-design]
see_also:
  - decisions/0094-bank-discovery-search-tool.decision.md
  - decisions/0095-channel-weighted-keyword-ranking.decision.md
  - decisions/0097-bank-discovery-skill-nudge.decision.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Concept: Bank Discovery — Search vs List

## What

The Bensyne MCP exposes two complementary bank-discovery tools:

- **`listMemoryBanks`** — enumerates **every** bank in the namespace.
  Diagnostic / full-inventory primitive. Wire shape
  `{banks: [...]}`.
- **`searchMemoryBank`** — free-text query → **ranked, filtered**
  subset of banks. Canonical discovery primitive. Wire shape
  `{matches: [...], total: <int>}`.

The two coexist; neither replaces the other.

## Why

The persona ecosystem scales with each new agent type (15 live banks
in the current environment and growing). Forcing every agent to
enumerate all banks before choosing made sense when the count was
fixed and small; once the count grows, agents need a discovery
primitive that filters by task relevance.

`searchMemoryBank` solves the discovery scaling problem without
breaking operators, observability scripts, and racochu reconcile
that depend on `listMemoryBanks`'s full-enumeration wire shape.

## Key Details

- **Use `searchMemoryBank` when:** you know what you're looking for
  (task keywords); you want a ranked subset; you're an agent doing
  task-start recall.
- **Use `listMemoryBanks` when:** you're an operator running
  diagnostics; you need the full inventory; `searchMemoryBank`
  returned no useful matches and you need to see what exists; you're
  running an observability script or racochu reconcile.
- **The skill nudge (`skills/bensyne/SKILL.md`) teaches:** "Call
  `searchMemoryBank(query='<starter keywords>')` to find the banks
  relevant to your task. For full enumeration / diagnostics, fall back
  to `listMemoryBanks()`."
- **Tool description says:** "Prefer this over `listMemoryBanks`
  for scoped discovery; `listMemoryBanks` remains available for
  diagnostics and full enumeration." (The description is the
  canonical teaching surface — agents that load Bensyne without
  loading the skill still learn the rule.)
- **Scoring intuition (see DEC-0096):** channel-weighted substring
  match with `description +2`, `name +1`, `derived +1`, plus a
  `+2` persona-match bonus when `agent_id` matches.