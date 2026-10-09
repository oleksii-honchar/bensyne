---
type: memory
title: "Bank dir mtime is refreshed by normal server activity"
createdAt: "2026-10-08T20:33:16Z"
updatedAt: "2026-10-08T20:33:16Z"
system: bensyne-mcp
tags: [bensyne-mcp, filesystem, ttl, cleanup, mnemosyne]
see_also:
  - "decisions/0116-session-bank-age-durable-signal.decision.md"
  - "decisions/0111-ephemeral-session-bank-cleanup.decision.md"
---

# Memory: Bank dir mtime is refreshed by normal server activity

## Fact

Opening/registering a memory bank refreshes the mtime of its directory **and** of its `mnemosyne.db` file. A single `listMemoryBanks` call touched all 586 bank dirs on puma.lan to the same minute (2026-10-08 20:04); `mnemosyne.db` mtime refreshed again at 20:11. ext4 birth time (crtime via `statx`) stayed stable (2026-09-22).

## Context

Measured live while diagnosing why the 30-day mtime-based TTL in the session-bank cleanup never expired (session evidence: `261008-2003-session-bank-cleanup/materials/evidence-cleanup-diagnostics.md`). Also: a macOS→Linux copy of `data/banks` (Aug 29–30) reset mtimes and left AppleDouble (`._*`) files — inert (filtered by `is_dir()`) but migration junk.

## Impact

Any mtime-based age/TTL scheme is unusable for banks. Use creation markers or filesystem crtime; never trust dir or db-file mtime for retention decisions.
