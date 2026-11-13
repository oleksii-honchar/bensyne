---
type: decision
id: DEC-0125
system: racochu
title: "ExcludeReconciliation Generalized to Out-of-Scope Cleanup — Mass-Forget Guard Covers Allow-List Rollouts for Free"
status: accepted
createdAt: "2026-11-13T16:33:29Z"
updatedAt: "2026-11-13T16:33:29Z"
tags: [racochu, reconciliation, mass-forget-guard, migration, scope-narrowing]
supersedes: []
superseded_by: []
see_also:
  - decisions/0077-ttl-mass-forget-guard.decision.md
  - decisions/0122-watch-source-include-allowlist.decision.md
  - concepts/0028-ingestion-scope-filtering.concept.md
  - runbooks/0013-include-allowlist-rollout-guarded-forget.runbook.md
  - specifications/0011-watch-source-include-allowlist.spec.md
---

# DEC-0125: Scope-Narrowing Cleanup Generalization (session ADR-6)

## Context

Excludes (and now allow-lists) only prevent **future** ingestion; already-ingested files
remain. An `include` rollout IS a scope-narrowing event: previously-ingested files fall
out of scope and their memories should be forgotten. The `ExcludeReconciliationService`
plus the mass-forget guard (threshold 20, explicit `RACOCHU_RECONCILE_FORCE_FORGET=1`
consent — pattern established DEC-0078, reuse precedent of the TTL design) already exist
to close exactly that gap safely.

## Decision

One cleanup path: the reconciliation selection becomes
`out-of-scope ⇔ (hasInclude ∧ ¬isPathIncluded) ∨ isPathExcluded`, evaluated against the
tracked absolute path (log/summary wording generalized to `outOfScopeMatched`; the
`ReconciliationSummary` shape was kept wire-compatible). The guard's threshold, consent
env-var, and semantics are untouched — its candidate set is now the out-of-scope set, so
allow-list rollouts are covered by the same refusal→consent flow without new machinery.

## Alternatives Considered

- **"Allow-list only prevents future ingestion — operator cleans up manually"** — leaves
  a second undocumented discovery path for exactly the pain the service was built for → rejected.
- **A second cleanup service for include rollouts** — duplicate machinery; contrast the
  deliberate reuse precedent in the TTL design → rejected.

## Consequences

Rollout forgetting never happens silently (irreversibility guarded; standing rule: no
destructive operation without explicit owner action). Measured first-rollout candidate set
(2026-11-13): ≈1661 tracked files predicted to refuse on first restart (>20), zero
forgotten until consent. Reverting config restores ingestion; forgotten memories are
re-ingestable from disk via force-reprocess.
