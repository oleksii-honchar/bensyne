---
type: index
title: "Shared Protocol ADRs"
createdAt: "2026-08-16"
updatedAt: "2026-08-16"
tags: []
---

# Shared Protocol ADRs

Cross-system architectural decisions for the Bensyne monorepo (bensyne-mcp + racochu) — the MCP protocol boundary. ID series: `ADR-SYS-NNNN`. Per-system ADRs live under `systems/bensyne-mcp/adrs/` and `systems/racochu/adrs/`.

## Nodes

### MCP Protocol

- [[0001-namespace-registration-protocol]] (ADR-SYS-0001) — External systems self-describe their memory banks; registration happens at startup via MCP
- [[0002-namespace-parameter-enforcement]] (ADR-SYS-0002) — Memory-bank parameter is required for all memory operations — no implicit default bank
- [[0003-in-memory-namespace-registry]] (ADR-SYS-0003) — In-memory `Dict[str, str]` bank registry, no persistence, re-registered on startup
