---
type: memory
title: "MCP Tool Description Is the Canonical Teaching Surface"
createdAt: "2026-08-28T12:58:00Z"
updatedAt: "2026-08-31T12:40:34Z"
system: shared
tags: [mcp, design-discipline, agent-nudge]
see_also:
  - decisions/0094-bank-discovery-search-tool.decision.md
  - decisions/0100-mcp-tool-descriptions-resolved-user-banks.decision.md
  - decisions/0101-search-memory-bank-user-suffixed-inclusion.decision.md
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

**Second confirming incident (2026-08-31):** stale descriptions did
not merely fail to teach the right behaviour — they *actively
misdirected* it. The `recallMemory`/`rememberMemory` descriptions
named the emptied legacy `default` and `agent-sessions` banks as
the user-profile/prior-context banks. An architect agent issued
recalls in the **same turn as skill loading**, so bank choice came
from the catalog description before the skill's bank-resolution
contract was absorbed; all recalls hit empty shells
(`results: []`). Fixed by DEC-0101 (description rewrite) +
DEC-0102 (user-bank surfacing). Two additional lessons:
(a) *timing* — a description is read before skill text, so a
wrong description cannot be corrected by skill loading in the
same turn; (b) *deployment lag* — after the code fix was
committed, the live server's runtime catalog kept teaching legacy
banks until the server was restarted with the new image. The
teaching surface is only as correct as the **deployed** schema.

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