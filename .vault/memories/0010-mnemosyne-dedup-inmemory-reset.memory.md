---
type: memory
system: racochu
title: "Mnemosyne dedup is in-memory only — resets on restart"
createdAt: "2026-07-31T07:30:00Z"
updatedAt: "2026-07-31T07:30:00Z"
tags: [mnemosyne, dedup, restart]
see_also: []
---

# Mnemosyne Dedup In-Memory Reset

**Fact:** Mnemosyne MCP client deduplication is in-memory only — process restart resets the set.

**Context:** Chunker restarts with stale file list → re-chunks all files. Mnemosyne handles dedup at storage level, but duplicate processing increases load.

**Impact:** Transient duplicate processing expected on restart. For large watch folders, consider persistent tracking or Mnemosyne-level dedup improvements.
