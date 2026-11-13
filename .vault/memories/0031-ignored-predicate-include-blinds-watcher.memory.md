---
type: memory
system: racochu
title: "Put an Extension Allow-List in chokidar's ignored Predicate and the Watcher Goes Blind to Directories"
createdAt: "2026-11-13T16:33:29Z"
updatedAt: "2026-11-13T16:33:29Z"
tags: [chokidar, picomatch, file-watcher, allow-list, probing]
see_also:
  - decisions/0122-watch-source-include-allowlist.decision.md
  - memories/0023-chokidar-dot-root-self-exclusion.memory.md
  - concepts/0028-ingestion-scope-filtering.concept.md
---

# Memory: Watcher Blindfold Hazard & Path-Base Parity (probed facts, 2026-11-13)

**Fact 1.** Extension-style patterns (`**/*.md`) never match directory paths
(picomatch, repo's own behavior, probe script on record). Putting such patterns into
the chokidar `ignored` predicate ignores EVERY directory — the watcher descends
nothing and ingests nothing. Scope filtering for allow-lists therefore lives in the
event handlers, not the `ignored` predicate (DEC-0122 invariant I2; e2e guard exists).

**Fact 2.** With the repo's `normalizePattern` (`**/` prefix) + `dot:true`, the same
pattern set matches BOTH root-relative and ABSOLUTE paths identically, so one config
pattern set safely serves watcher (absolute) and batch (root-relative) enforcement
points. An unnormalized pattern (e.g. bare `.md`) matches nothing — normalization is
mandatory for include lists too.
