---
type: vault-home
title: "Bensyne Vault"
createdAt: "2026-08-16"
updatedAt: "2026-08-16"
tags: []
---

# Bensyne Vault

The single durable knowledge vault for the whole Bensyne monorepo (bensyne-mcp + racochu). Created 2026-08-16 by consolidating the two per-app vaults into one root vault.

## Layout

- **Shared/cross-system knowledge** lives in the root areas — decisions, memories, and architecture that span the MCP protocol boundary between the two systems:
  - [Shared Protocol ADRs](adrs/_index.md) — `ADR-SYS-NNNN` series
  - [Shared Transport Memories](memories/_index.md) — `MEM-SYS-NNNN` series
  - [Shared Architecture Maps](architectures/_index.md) — whole-system C4 views
- **Per-system specificity** lives under `systems/` — one sub-vault per app, with its own local ID series:
  - [Bensyne MCP System Vault](systems/bensyne-mcp/_Vault-Home.md) — `apps/bensyne-mcp` (Python + FastMCP memory server)
  - [Racochu System Vault](systems/racochu/_Vault-Home.md) — `apps/racochu` (Node.js + NestJS ingestion server)

## ID Series — Do Not Confuse

Three ID series coexist in this vault. An ID matching another area's series is **not** a duplicate — each series is scoped to its own area:

| Series | Scope | Location | Example |
|--------|-------|----------|---------|
| `ADR-NNNN` / `MEM-NNNN` (local) | bensyne-mcp only | `systems/bensyne-mcp/` | `ADR-0001` — Namespace Registration Tool |
| `ADR-NNNN` / `MEM-NNNN` (local) | racochu only | `systems/racochu/` | `ADR-0001` — (different decision, racochu-local) |
| `ADR-SYS-NNNN` / `MEM-SYS-NNNN` | shared, cross-system | root `adrs/`, `memories/` | `ADR-SYS-0001` — Memory Bank Registration Protocol |

The two local series are **independent number spaces** — e.g. bensyne-mcp `ADR-0001` and racochu `ADR-0001` are different ADRs. The `ADR-SYS-`/`MEM-SYS-` series exists precisely to make shared scope explicit and to avoid `id` collisions. Cross-references between series use `see_also` relative paths, never ID matching.
