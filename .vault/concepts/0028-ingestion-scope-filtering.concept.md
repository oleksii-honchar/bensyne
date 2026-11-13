---
type: concept
system: racochu
title: "Ingestion Scope Filtering — Four Enforcement Points, One Matcher, Two Path Bases"
createdAt: "2026-11-13T16:33:29Z"
updatedAt: "2026-11-13T16:33:29Z"
tags: [racochu, ingestion, filtering, glob-matcher, watch-source]
see_also:
  - concepts/0012-processing-model.concept.md
  - decisions/0122-watch-source-include-allowlist.decision.md
  - decisions/0123-reprocess-edges-exclude-alignment.decision.md
  - decisions/0125-reconciliation-out-of-scope-semantics.decision.md
  - memories/0031-ignored-predicate-include-blinds-watcher.memory.md
---

# Concept: Ingestion Scope Filtering

## What
Every file entering racochu memory passes path-based scope filtering at four
independent enforcement points (EP1 live watcher, EP2 force-reprocess batch scan,
EP3 reprocess-edges scan, EP4 startup reconciliation), all composing the SAME pure
primitives in `src/application/glob-matcher.ts`. The composition (DEC-0122):
`ingest ⇔ hardGuards ∧ (no include ∨ included) ∧ ¬excluded`.

## Why
Two path bases exist (watcher events carry absolute paths; batch scans root-relative)
and enforcement points historically grew their own matchers that drifted — glob-matcher
exists as the deliberate single source of truth. Scope changes are dangerous because
narrowing forgets existing memories; cleanup therefore runs through the guarded
reconciliation path (DEC-0125), never implicitly.

## Key Details
- Hard guards (`.git`, `node_modules`, `.DS_Store`, `Thumbs.db`, `.env*`) are a
  separate always-on layer, never overridable by either list.
- Filters are evaluated against FILES only at every EP; directory descent is
  exclude-only (extension globs never match directories — see memory 0031).
- Watcher-specific shape: the chokidar `ignored` predicate holds excludes + hard
  guards + root guard (DEC-0088); include lives in the event handlers so directories
  keep being watched; UNLINK stays unfiltered on purpose (it is the only forget path
  for a tracked file deleted while out of scope).
- `**/`-normalized picomatch patterns (`dot:true`) behave identically on both path
  bases — that parity is what allows one pattern set per source.
- The content-classifier is a SECOND, post-read gate (content-sniffing machine dumps);
  it complements path filtering, never replaces it — it cannot bound watch cost.
- Scope narrowing ⇒ forgetting: tracked out-of-scope files are cleaned by the
  reconciliation service behind the mass-forget guard (threshold 20, explicit consent
  env-var; shared mechanism with the TTL design, DEC-0078).
