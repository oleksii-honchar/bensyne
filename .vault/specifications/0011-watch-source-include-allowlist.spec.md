---
type: specification
system: racochu
kind: feature
title: "Watch-Source Include Allow-List"
status: completed
createdAt: "2026-11-13T16:33:29Z"
updatedAt: "2026-11-13T16:33:29Z"
owner: ""
target: ""
see_also:
  - decisions/0122-watch-source-include-allowlist.decision.md
  - decisions/0123-reprocess-edges-exclude-alignment.decision.md
  - decisions/0124-remove-dead-watchsource-entity-fields.decision.md
  - decisions/0125-reconciliation-out-of-scope-semantics.decision.md
  - concepts/0028-ingestion-scope-filtering.concept.md
  - runbooks/0013-include-allowlist-rollout-guarded-forget.runbook.md
---

# Specification: Watch-Source Include Allow-List (implemented, landed at 7464e39)

## Goal & Back-Compat Contract
Per-source positive allow-list replacing long deny-lists. Contract: every config that
parses today parses identically and behaves byte-identically at all four enforcement
points; no schema default for include; exclude/DEFAULT_IGNORE_GLOBS/root guard
(DEC-0088)/content-classifier unchanged.

## Config Contract
`include: z.array(z.string()).optional()` on shared `watchSourceShape`; entry-gate
superRefine rejects only normalized-equal include∩exclude pairs (names both keys +
pattern, path ['include']); never on the internal seam.

## Matching Contract (glob-matcher — the single source of truth)
isPathIncluded (empty/absent allow-list allows everything); isPathInScope =
hardGuards ∧ (no include ∨ included) ∧ ¬excluded. Truth table locked by unit tests.
Invariants: I1 hard guards never re-admitted; I2 include evaluated against files only —
descent stays exclude-only; I3 one normalized pattern set serves absolute (watcher) and
root-relative (batch) path bases.

## Enforcement-Point Wiring
EP1: scope check inside handleFileAdded/handleFileChanged (absolute path); ignored
predicate untouched; handleFileDeleted deliberately UNFILTERED (only forget path for a
tracked out-of-scope delete — EP4 skips files absent from disk).
EP2: file-emit branch → isPathInScope (root-relative); descent branch exclude-only.
EP3: stub wired per DEC-0123 (descent exclude-only, emit scope-checked).
EP4: selection generalized to out-of-scope per DEC-0125; guard unchanged.

## Operator Migration (measured 2026-11-13 — treat counts as context, the diff as the invariant)
agent-sessions source: include ['**/*.md','**/*.mmd'] + 7 deliberately-residual
directory excludes replaces the 38-glob block; fixture-verified delta vs old config =
0 added / 404 documented stragglers dropped (bounded set enumerated in the session's
data-ingestion-scope-census.json). The 7 residual excludes stay because their trees
would otherwise match the include list by extension — dropping them is a silent
behavior change, not a simplification. obsidian source migration BLOCKED on a stale
configured path (operator-side finding, unrelated defect).

## Rollout Guard (the HIGH breakage scenario)
Include-narrowing → restart → reconciliation refuses when out-of-scope tracked files
exceed threshold 20, logs counts, forgets nothing; operator executes
RACOCHU_RECONCILE_FORCE_FORGET=1 explicitly. See runbook 0013.

## Verification (all green in review at 7464e39)
Truth-table + I1/I2/I3 named tests; parse-identity fixtures; EP-level include tests;
EP3 pre/post red evidence; UNLINK lock; watcher include-scope e2e (no blindfold);
config-migration set-diff gate; zero new failures vs recorded baseline.
