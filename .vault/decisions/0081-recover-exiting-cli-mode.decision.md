---
type: decision
id: DEC-0082
system: racochu
title: "--recover as an Exiting CLI Mode with --source Support"
status: accepted
createdAt: "2026-08-26T07:18:26Z"
updatedAt: "2026-08-26T07:18:26Z"
tags: [recover, cli, main-routing, exit-after-pass]
supersedes: []
superseded_by: []
see_also:
  - decisions/0083-recover-filetracker-known-files.decision.md
  - decisions/0060-sequential-file-processing.decision.md
  - specifications/0007-racochu-recover-mode.spec.md
---

# DEC-0082: --recover as an Exiting CLI Mode with --source Support

## Context

Recover must process only DB-known files and exit after the pass. Existing modes
(`--resume`/`--force-reprocess`) exit only when combined with `--process-only`; watch is default.
`main.ts` routing order verified: `help/version → exclude-reconciliation → TTL → resume →
force-reprocess → process-only → watch`.

## Decision

Add `--recover` flag to `CliArgsService` (default `false`, sets `watch=false`). `main.ts` routes
it before the watch start: `recoverAll(sources)` or `recoverSource(sourceId, sources)` with
`-s/--source`, then `waitForEmpty → close → exit(0)` — always, regardless of `--process-only`.
Exclude reconciliation + TTL sweep still run at startup. `--dry-run` reports missing chunks
without submitting.

## Alternatives Considered

- Make recover a subcommand (`racochu recover`) — rejected: the codebase uses flag-based modes.
- Reuse `--resume` with a new flag — rejected: resume is filesystem-scan + shallow local-only;
  recover is DB-anchored + MCP-verified. Sibling service is cleaner.

## Consequences

- `ParsedCliArgs` grows one boolean; help text updated; e2e asserts exit-after-pass.
- ⚠️ Known gap (review medium finding): recover currently exits `0` even when every file errors —
  the spec's "abort with clear message" for a missing tool is not honored. Tracked as follow-up.
