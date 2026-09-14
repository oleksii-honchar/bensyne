---
type: memory
title: "Mnemosyne Native valid_until Is Soft Expiry — Not Per-Source Retention or Auto-Sweep"
createdAt: "2026-08-25T13:45:19Z"
updatedAt: "2026-09-14T16:35:00Z"
system: racochu
tags: [mnemosyne, ttl, retention, gotcha]
see_also: ["specifications/0006-source-ttl-sweep.spec.md", "decisions/0073-ttl-sweep-racochu-side.decision.md", "decisions/0108-per-session-memory-banks.decision.md"]
---

# Fact: Mnemosyne Native valid_until Is Soft Expiry — Not Per-Source Retention or Auto-Sweep

Mnemosyne (`mnemosyne-memory>=3.15.1,<4.0.0`) has a per-memory `valid_until`
column (YYYY-MM-DD) on working/episodic/canonical_facts/triples tables.
`remember(..., valid_until="...")` sets it at write time; `mnemosyne_invalidate`
MCP tool stamps `valid_until = CURRENT_TIMESTAMP`; recall/get_context/
get_all_memories filter out expired rows. Rows remain in the DB — excluded from
retrieval, not deleted.

## Context

As of 2026-09-14, `valid_until` is **only partially plumbed** in Bensyne:

- The `rememberMemory` MCP tool schema (`apps/bensyne-mcp/src/app.py`) declares a
  `valid_until` parameter ("Optional. ISO-8601 datetime when this memory becomes
  obsolete and should be dropped."), and the tool description instructs agents how
  to use it.
- `get_persona_status_use_case.py` reads Mnemosyne's `valid_until` column to report
  expired occasional memories (`_valid_until_in_past`, `expired_occasional_memories`).
- **However, the write path drops it:** `MnemosyneClient.save()` calls
  `remember(content, source, importance)` with **no** `valid_until`; the domain
  `Memory` entity, `memory_model.py`, and `remember_memory_use_case.py` have no
  `valid_until` field. The parameter predates this session (commit `041eb6a`,
  2026-08-20) and is accepted-but-ignored on write.

So the original statement still holds for the write path: Bensyne never passes
`valid_until` to Mnemosyne on `save()`. The tool surface advertises it, but the
value is dropped before Mnemosyne is called. No automatic time-based sweep exists
in mnemosyne — `hygiene` is noise detection, not TTL.

## Impact

Mnemosyne's native mechanism cannot satisfy "TTL per source → 1y → delete old
memories with files" alone. The racochu-side sweep + `forgetByFile` (hard
delete via bensyne) is the only complete path. `valid_until` could optionally
complement it (soft-exclude from recall before hard deletion), but is not
required.
