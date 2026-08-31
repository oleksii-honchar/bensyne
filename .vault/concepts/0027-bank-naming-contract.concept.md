---
type: concept
title: "Bank Naming Contract — User-Suffixed vs Legacy"
createdAt: "2026-08-31T12:40:34Z"
updatedAt: "2026-08-31T12:40:34Z"
system: bensyne-mcp
tags: [mcp, bank-discovery, naming, racochu]
see_also:
  - decisions/0100-mcp-tool-descriptions-resolved-user-banks.decision.md
  - decisions/0101-search-memory-bank-user-suffixed-inclusion.decision.md
  - decisions/0094-bank-discovery-search-tool.decision.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Concept: Bank Naming Contract — User-Suffixed vs Legacy

## What

The canonical memory-bank naming contract for Bensyne MCP + Racochu:

| Bank | Meaning | Resolved from |
|---|---|---|
| `user_<id>` | User profile (read + write) | `yq '.user.bank // ("user_" + .user.id)' ~/.config/racochu.yaml` |
| `agent-sessions_{user_id}` | Prior session context (recall-only) | `user.id` as suffix of the bank name |
| `default` | Legacy shell (deleted 2026-08-29) | — do not use |
| `agent-sessions` | Legacy shell (deleted 2026-08-29) | — do not use |
| `vault` | Project knowledge (recall-only) | Racochu watchSource |
| `obsidian` | Personal notes (recall-only) | Racochu watchSource |
| `agent-persona_<agent>` | Persona decision tree + occasional memories | Racochu node files + agent writes |

## Why

The 2026-08-29 migration emptied the legacy `default` and
`agent-sessions` banks and introduced per-user suffixed banks, but
tool descriptions, skills, and rules kept naming the legacy banks for
a while — until agents demonstrably followed the stale names into
empty shells (2026-08-31 incident, DEC-0101/DEC-0102). The naming
contract needs one canonical reference because it is taught from
four surfaces: the MCP tool schema, `skills/bensyne/SKILL.md`,
`skills/agent-persona-base/SKILL.md` (Phase 0.5), and
`~/.rules/olho/always-apply/bensyne-memory.mdc`.

## Key Details

- **No legacy fallback.** An empty `user_<id>` /
  `agent-sessions_{user_id}` bank means "no context yet" (the bank
  populates on the next Racochu ingest) — never fall back to
  `default`/`agent-sessions`.
- **The name prefix is a system signal.** DEC-0102's floor-score
  inclusion keys on `user_` / `agent-sessions_` prefixes; renaming
  user banks off this pattern breaks discovery.
- **Raw id, no sanitization.** Hyphens and underscores are both
  allowed in `<id>` (e.g. `agent-sessions_oleksii`).
- **Typos create banks.** A mistyped bank name (e.g. the stray
  `user_oleksiil` observed 2026-08-31) registers as a distinct
  namespace — there is no correction mechanism short of operator
  cleanup.
