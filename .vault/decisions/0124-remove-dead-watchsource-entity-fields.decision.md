---
type: decision
id: DEC-0124
system: racochu
title: "Remove Dead WatchSource include/ignorePatterns Scaffolding — WatchSourceConfig Is the Seam"
status: accepted
createdAt: "2026-11-13T16:33:29Z"
updatedAt: "2026-11-13T16:33:29Z"
tags: [racochu, domain, entity, dead-code]
supersedes: []
superseded_by: []
see_also:
  - decisions/0122-watch-source-include-allowlist.decision.md
  - architectures/racochu/code/0001-domain-aggregates.code.md
  - concepts/0028-ingestion-scope-filtering.concept.md
---

# DEC-0124: Dead `WatchSource.include` Disposition (session ADR-5)

## Context

`domain/watch-source.entity.ts` carried `include` (and `ignorePatterns`) since the
initial commit, but `WatchSource.of(...)` was constructed **only in its own test files** —
zero production consumers (symbol sweep, re-confirmed at landing). The pipeline consumes
`WatchSourceConfig` (config-schemas) end-to-end. Shipping a config field named `include`
alongside an unwired entity twin of the same name with different behavior re-creates
exactly the drift class `glob-matcher` was created to prevent.

## Decision

Delete both fields (schema, `toJson`, getters) from the entity and its two test files.
The config type is the seam. If a real WatchSource aggregate is ever introduced, re-add
a field carrying DEC-0122 semantics from day one.

## Alternatives Considered

- **Adopt the entity as the pipeline seam** — invents a construction path just to
  justify dead fields → rejected.
- **Keep the fields "reserved"** — two same-named concepts, one unwired: drift waiting
  to happen → rejected.

## Consequences

Domain model honest; zero runtime impact (measured); the C4 code doc, which already
described the entity without these fields, becomes truthful again. Reverting = git revert.
