---
type: adr
id: ADR-0026
title: "Use native-machine-id for Hardware ID Detection"
status: accepted
createdAt: "2026-08-07T18:01:00Z"
updatedAt: "2026-08-07T18:01:00Z"
tags: [hardware-id, native-machine-id, cross-device]
supersedes: []
superseded_by: []
see_also:
  - "adrs/0021-file-hash-deduplication-metadata.adr.md"
  - "adrs/0023-filetracker-schema-extension.adr.md"
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# ADR-0026: Use native-machine-id for Hardware ID Detection

## Context

Hardware ID is needed to track which device ingested each file, enabling audit of file distribution across devices.

## Decision

Use `native-machine-id` npm module for hardware ID detection. The `HardwareIdDetectorService` wraps this module, caches the result on first call, and falls back to `crypto.randomUUID()` on detection failure.

**Detection paths (from module):**
- macOS: `IOPlatformExpertDevice` UUID via IOKit
- Linux: `/sys/class/dmi/id/product_uuid`
- Windows: Native API

## Alternatives Considered

1. **Custom shell commands** — platform-specific, slower, error-prone
2. **node-machine-id** — slower, uses child processes
3. **system-uuid** — very low usage, not well-maintained

## Consequences

- **Positive:** Fast, reliable, cross-platform, no admin privileges required, no child process spawning
- **Negative:** Additional npm dependency
- **Mitigation:** Well-maintained module with native bindings; fallback to randomUUID ensures non-fatal failures
