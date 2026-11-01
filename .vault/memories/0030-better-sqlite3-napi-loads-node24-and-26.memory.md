---
type: memory
system: racochu
title: "better-sqlite3 13.x Is N-API: Loads Under Node 24 and 26 — the ABI 147-vs-137 Blocker Claim Is Stale"
createdAt: "2026-11-01T13:54:35Z"
updatedAt: "2026-11-01T13:54:35Z"
tags: [better-sqlite3, node, n-api, abi, environment]
see_also:
  - decisions/0028-file-memory-tracking-prisma-sqlite.decision.md
  - runbooks/0004-prisma-setup.runbook.md
---

# better-sqlite3 13.x Is N-API: Loads Under Node 24 and 26

## Fact

`better-sqlite3@13.0.3` (as vendored in `apps/racochu/node_modules`) ships
`prebuilds/darwin-arm64.node` via **N-API**; empirically loads (`new Database(":memory:")` via
absolute require path) under **both** Node v24.20.0 (NODE_MODULE_VERSION 137) and v26.8.1 (147).
The historical "ERR_DLOPEN_FAILED 147 vs current 137" claim is **not reproducible** on the source
tree and is retired (the npx-cache copy it referenced no longer exists).

## Context

Captured 2026-10-31 while diagnosing the racochu duplicate re-ingestion issue
(session `261031-0953-bootstrap-researcher`, findings §5). The ABI mismatch was a standing
assumption in operator lore; it blocked nothing that day — the run processed files normally
through MCP init + registration.

## Impact

Do **not** treat better-sqlite3 ABI as a suspect in racochu failures on this machine.
Residual footgun to revisit only if better-sqlite3 ever drops N-API or a `node-gyp` rebuild runs:
root `.nvmrc` pins Node 26 and `package.json engines.node >=26`, while the default shell Node is
v24.20.0 — harmless while N-API holds.
