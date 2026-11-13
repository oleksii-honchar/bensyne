---
type: decision
id: DEC-0123
system: racochu
title: "reprocess-edges Scan: Wire the Unfinished Exclude Stub — Edge Reprocessing Narrows to In-Scope Files"
status: accepted
createdAt: "2026-11-13T16:33:29Z"
updatedAt: "2026-11-13T16:33:29Z"
tags: [racochu, reprocess-edges, filtering, behavior-change]
supersedes: []
superseded_by: []
see_also:
  - decisions/0122-watch-source-include-allowlist.decision.md
  - concepts/0028-ingestion-scope-filtering.concept.md
  - specifications/0011-watch-source-include-allowlist.spec.md
---

# DEC-0123: Edge-Scan Filtering Alignment (session ADR-3)

## Context

Verified at pin `6ed930b`: `reprocess-edges.service.ts` performed **no filtering at
all** — its exclude check is an empty stub that was born unfinished in commit `be40a0f`
(the stub's own comment states the intended behavior: skip excluded paths via the shared
glob matcher). The working assumption that all four enforcement points already shared one
predicate was false for EP3.

## Decision

Implement the stub's documented intent as part of the allow-list feature: descent stays
exclude-only (mirroring EP2), file emission uses the shared scope composition (DEC-0122).
This is a **behavior change** — edge reprocessing narrows from all scanned files to
in-scope files — so it was to ride as its own revertible commit (the owner later
squashed the landing; single-op revert of the whole feature is now the granularity).

## Alternatives Considered

- **Leave EP3 unfiltered forever** — then "identical behavior at all enforcement points"
  is unachievable and include would silently skip EP3 → rejected.
- **Gate behind a flag** — extra config surface for a one-line alignment → rejected.

## Consequences

Edge reprocessing no longer churns `.git`/junk files (cost win, fewer phantom edge
considerations). Archaeology (stub intent in `be40a0f`) proves no intentional design is
being broken. Narrowing is bounded and revertible; new EP3 tests are the alignment lock.
