---
type: adr
id: ADR-0007
title: "Configuration Management"
status: accepted
createdAt: "2026-07-30T23:00:00Z"
updatedAt: "2026-07-31T07:30:00Z"
tags: [infrastructure, configuration]
see_also: []
---

# ADR-0007: Configuration Management

## Context

Need to manage configuration for enhancement features while maintaining existing patterns.

## Decision

Extend existing Zod configuration schema (`config-schemas.ts`) with new enhancement settings. Root schema includes: watchSources, chunking, enhancement, enrichment, mcp, telemetry — all optional with defaults via `.transform()`.

Config loaded from:
- Production: `~/.config/rag-content-chunker.yaml`
- Development: `dev.yaml` via `APP_CONFIG_PATH` env var

## Alternatives Considered

1. **New configuration file** — Create separate enhancement config
2. **Environment variables** — Use environment variables for configuration
3. **Database configuration** — Store configuration in database

## Consequences

- **Positive**: Consistent config management, familiar YAML pattern, Zod validation
- **Negative**: Schema grows more complex with each feature
- **Mitigation**: Each section independently optional with clear defaults
