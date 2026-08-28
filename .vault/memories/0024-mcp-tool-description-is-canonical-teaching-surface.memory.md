---
type: memory
title: "MCP Tool Description Is the Canonical Teaching Surface"
createdAt: "2026-08-28T12:58:00Z"
updatedAt: "2026-08-28T12:58:00Z"
system: shared
tags: [mcp, design-discipline, agent-nudge]
see_also:
  - decisions/0094-bank-discovery-search-tool.decision.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Memory: MCP Tool Description Is the Canonical Teaching Surface

## Fact

In Bensyne MCP (and FastMCP-3.x tool registration generally), the
**tool's `description` string** is the authoritative place to teach
agents how and when to use the tool — not the skill text and not the
docs.

## Context

The Bensyne canonical skill (`skills/bensyne/SKILL.md`) previously
mandated `listMemoryBanks` as the agent's entry-point discovery tool
in six places. A literal test assertion
(`test_mcp_tool_descriptions.py::test_list_memory_banks_encodes_discovery_first`)
further cemented the nudge by asserting the tool description
literally contained `"first"` / `"discover"` / `"before"`. When the
team added `searchMemoryBank`, the lesson had to be encoded in the
**new tool's description**, not just in skill text — because agents
that use Bensyne without loading the skill (possible via direct MCP
calls) would never see the skill-only guidance.

## Impact

- When redesigning an MCP tool's role in an agent workflow, edit
  **both** the skill text and the tool description; assume the skill
  text may not be loaded.
- Replace "negative" assertions that cement the wrong behaviour
  (e.g. "must say 'first'") with "positive" assertions on the new
  tool (e.g. "must say 'prefer'"). Dropping a gate without replacing
  it leaves the wrong wording able to drift back in.
- Per-tool parameter descriptions (`_MEMORY_BANK_*_DESC` constants)
  are also a propagation surface — softening them in one place fixes
  every per-tool docstring that references them.