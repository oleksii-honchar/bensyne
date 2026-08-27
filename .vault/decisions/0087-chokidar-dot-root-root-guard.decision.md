---
type: decision
id: DEC-0088
system: racochu
title: "Chokidar Dot-Root Watch Guard — Never Exclude the Watched Root"
status: accepted
createdAt: "2026-08-27T18:45:00Z"
updatedAt: "2026-08-27T18:45:00Z"
tags: [racochu, chokidar, file-watcher, dot-root, exclude, bugfix]
supersedes: []
superseded_by: []
see_also:
  - decisions/0088-chokidar-watcher-ready-log.decision.md
  - memories/0023-chokidar-dot-root-self-exclusion.memory.md
  - runbooks/0003-troubleshooting.runbook.md
---

# DEC-0088: Chokidar Dot-Root Watch Guard — Never Exclude the Watched Root

## Context

`~/.agent-sessions` is a dot-named watch source root. The exclude pattern `'**/.*'`
(added 2026-08-24, retained 2026-08-27) compiles to a regex that matches the root path
itself. chokidar evaluates `ignored(root)` before descending; when it is `true`, chokidar
watches nothing under the root, so the live watcher emits zero events for the source.
Startup force-reprocess/resume scans still ingest pre-existing files, masking the failure.
Last live `agent-sessions` event was 2026-08-26 20:42:50 (log 127); daemons from log 128
(`sources=12`, 20:42:51) through 153 were silent.

## Decision

In `FileWatcherService.startWatchingSource()` (`apps/racochu/src/infrastructure/services/file-watcher.service.ts`),
never treat the exact resolved root as excluded: normalize trailing slashes on both sides
and short-circuit the compiled ignore-regex test for the root itself.

```ts
const normalizedRoot = resolvedPath.replace(/\/+$/, '');
// ...
ignored: (candidatePath: string) =>
  candidatePath.replace(/\/+$/, '') !== normalizedRoot &&
  ignoreRegexes.some(regex => regex.test(candidatePath)),
```

The guard is behavior-preserving for descendants (only the exact root short-circuits) and
for non-dot roots (no-op there). Config hardening (replacing blanket `'**/.*'` with
explicit per-directory dot excludes) is endorsed as defense-in-depth but tracked as an
operator-side edit, not part of the code ADR. Tracked follow-up (ADR-5): the redundant
second `start()` between `onApplicationBootstrap()` and `main.ts:200` — deliberately not
bundled.

## Alternatives Considered

- **Config-only fix** (remove `'**/.*'`): insufficient — any future dot-root or
  dot-matching exclude could regress; does not fix the class of bug.
- **Shared `isPathExcludedWithRootGuard` helper in `glob-matcher.ts`**: deferred —
  force-reprocess already uses relative paths and is unaffected; single-use abstraction.
- **Changing normalization semantics**: too broad — would alter the well-tested
  dotfile-matching contract for ALL consumers.

## Consequences

- Positive: minimal, fault-location-exact fix; protects any dot-root now and in the
  future; no API/schema/dependency change.
- Regression proof: `apps/racochu/src/e2e/watcher-dot-root/watcher-dot-root.integration.test.ts`
  (real chokidar on a temp dot-named root + `'**/.*'` predicate; RED without the guard,
  GREEN with it). Unit tests at
  `file-watcher.service.test.ts` ("never ignores the watched root itself…") lock the
  predicate contract.
- Negative/risk: none identified beyond requiring the regression tests to stay green.