---
type: decision
id: DEC-0089
system: racochu
title: "Per-Source Watcher `ready` Logging for Detectability"
status: accepted
createdAt: "2026-08-27T18:45:00Z"
updatedAt: "2026-08-27T18:45:00Z"
tags: [racochu, file-watcher, observability, chokidar, logging]
supersedes: []
superseded_by: []
see_also:
  - decisions/0087-chokidar-dot-root-root-guard.decision.md
  - runbooks/0003-troubleshooting.runbook.md
---

# DEC-0089: Per-Source Watcher `ready` Logging for Detectability

## Context

The only observable signal of the dot-root failure was the absence of live events — there
was no startup confirmation that a source was actually being watched. A silent watcher is
not diagnosable.

## Decision

Attach a chokidar `ready` listener per source in `startWatchingSource()`
(`apps/racochu/src/infrastructure/services/file-watcher.service.ts`) that logs once:

```ts
emitter.on('ready', () => {
  this.logger.info(`Watcher ready; source="${source.id}", path="${normalizedRoot}"`);
});
```

A source that never logs `ready` is immediately diagnosable as not watched.

## Alternatives Considered

- **Liveness watchdog** (periodic probe write + assert ingestion): more powerful but adds
  operational complexity (probe lifecycle, noise, edge cases) — deferred/optional.
- **Enriching startup summary with watcher counts**: helpful but does not prove the
  watcher is live; `ready` is the chokidar-native proof.

## Consequences

- **Positive:** cheap, observable startup proof per source; failure mode flips from
  "silent" to "missing ready log".
- **Negative:** log-line addition only; `ready` does not fire on watcher errors — the
  existing `error` listener covers that path.