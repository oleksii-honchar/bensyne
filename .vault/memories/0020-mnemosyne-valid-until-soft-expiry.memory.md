---
type: memory
title: "Mnemosyne Native valid_until Is Soft Expiry — Not Per-Source Retention or Auto-Sweep"
createdAt: "2026-08-25T13:45:19Z"
updatedAt: "2026-08-25T13:45:19Z"
system: racochu
tags: [mnemosyne, ttl, retention, gotcha]
see_also: ["specifications/0006-source-ttl-sweep.spec.md", "decisions/0073-ttl-sweep-racochu-side.decision.md"]
---

# Fact: Mnemosyne Native valid_until Is Soft Expiry — Not Per-Source Retention or Auto-Sweep

Mnemosyne (`mnemosyne-memory>=3.15.1,<4.0.0`) has a per-memory `valid_until`
column (YYYY-MM-DD) on working/episodic/canonical_facts/triples tables.
`remember(..., valid_until="...")` sets it at write time; `mnemosyne_invalidate`
MCP tool stamps `valid_until = CURRENT_TIMESTAMP`; recall/get_context/
get_all_memories filter out expired rows. Rows remain in the DB — excluded from
retrieval, not deleted.

## Context

Bensyne does not use `valid_until` at all (`MnemosyneClient.save()` calls
`remember(content, source, importance)` with no valid_until). No automatic
time-based sweep exists in mnemosyne — `hygiene` is noise detection, not TTL.

## Impact

Mnemosyne's native mechanism cannot satisfy "TTL per source → 1y → delete old
memories with files" alone. The racochu-side sweep + `forgetByFile` (hard
delete via bensyne) is the only complete path. `valid_until` could optionally
complement it (soft-exclude from recall before hard deletion), but is not
required.
