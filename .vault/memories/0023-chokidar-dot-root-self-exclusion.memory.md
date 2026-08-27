---
type: memory
system: racochu
title: "Chokidar Dot-Root Self-Exclusion — Exclude Glob Matching the Watched Root"
createdAt: "2026-08-27T18:45:00Z"
updatedAt: "2026-08-27T18:45:00Z"
tags: [chokidar, file-watcher, dot-root, exclude, bugfix]
see_also:
  - decisions/0087-chokidar-dot-root-root-guard.decision.md
  - memories/0014-chokidar-macos-dual-events.memory.md
  - runbooks/0003-troubleshooting.runbook.md
---

# Memory: Chokidar Dot-Root Self-Exclusion

## Fact

An exclude pattern like `'**/.*'` compiles to a regex that also matches a dot-named
watched root (e.g. `~/.agent-sessions`). Chokidar evaluates `ignored(root)` before
descending; `ignored(root) === true` ⇒ the watcher emits ZERO events for the entire
source, while startup force-reprocess/resume scans still ingest pre-existing files and
mask the failure.

## Context

Regression introduced 2026-08-24 when `'**/.*'` entered the `agent-sessions` source
excludes; retained through the 2026-08-27 rewrite. Live ingestion under the dot root
silently stopped (last `File added` 2026-08-26 20:42:50, log 127; silent daemons log
128–153). Companion to [[memories/0014-chokidar-macos-dual-events]] — that is the
event-duplication trap; this is the exclusion/predicate trap.

## Impact

Fixed in `FileWatcherService.startWatchingSource()` via the root guard (see
[[decisions/0087-chokidar-dot-root-root-guard]]): never exclude the normalized root
before testing ignore regexes. Verify any future dot-named source root against this trap
when adding blanket dotfile excludes.