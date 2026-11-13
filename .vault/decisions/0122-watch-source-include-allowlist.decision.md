---
type: decision
id: DEC-0122
system: racochu
title: "Per-Source Include Allow-List — Positive-List Field, One Composition in glob-matcher, Files-Only, Entry-Gate Shadow Rule"
status: accepted
createdAt: "2026-11-13T16:33:29Z"
updatedAt: "2026-11-13T16:33:29Z"
tags: [racochu, config, ingestion, allow-list, glob-matcher, chokidar, watch-source]
supersedes: []
superseded_by: []
see_also:
  - decisions/0025-configuration-management.decision.md
  - decisions/0075-ttl-config-ttl-days.decision.md
  - decisions/0087-chokidar-dot-root-root-guard.decision.md
  - decisions/0123-reprocess-edges-exclude-alignment.decision.md
  - decisions/0125-reconciliation-out-of-scope-semantics.decision.md
  - concepts/0028-ingestion-scope-filtering.concept.md
  - specifications/0011-watch-source-include-allowlist.spec.md
  - runbooks/0013-include-allowlist-rollout-guarded-forget.runbook.md
---

# DEC-0122: Per-Source `include` Allow-List (consolidates session ADR-1, ADR-2, ADR-4, ADR-7)

## Context

Operator ingestion control was deny-lists only: the two largest watch sources carried
38- and 32-glob exclude blocks (`~/.config/racochu.yaml`), growing with every new
tool-emitted file type. No allow-list primitive existed anywhere (code, config, vault,
prior sessions — all negative at pin `6ed930b`); chokidar has no native allow-list, so
enforcement must live at racochu's application layer. A dead domain-entity field named
`include` existed unwired (disposition: DEC-0124).

## Decision

1. **Field:** `include: z.array(z.string()).optional()` on the single shared
   `watchSourceShape`. Opt-in, never defaulted (DEC-0076/DEC-0078 idiom of
   `ttlDays`/`deleteDueFiles`); absent ⇒ today's behavior byte-identically.
2. **Composition (the only scope formula):**
   `ingest ⇔ hardGuards ∧ (no include ∨ included) ∧ ¬excluded` — implemented as exactly
   two pure exports plus the composition helper `isPathInScope` in
   `src/application/glob-matcher.ts` (the designated single source of truth — placing
   matching anywhere else recreates the historical per-enforcement-point drift).
   Every enforcement point (EP1 watcher, EP2 force-reprocess, EP3 reprocess-edges,
   EP4 exclude-reconciliation) composes this same helper; no local predicates at call sites.
3. **Hard guards are never overridden** (invariant I1): `.git`, `node_modules`,
   `.DS_Store`, `Thumbs.db`, `.env*` stay always-off regardless of include.
4. **`include` is evaluated against files only** (invariant I2): extension include
   patterns never match directories, so putting them into the chokidar `ignored`
   predicate would ignore every directory and disable the watcher (probed hazard).
   Directory descent/pruning stays exclude-only at EP2/EP3; EP1 keeps the scope check
   inside `handleFileAdded`/`handleFileChanged`; `handleFileDeleted` stays unfiltered
   on purpose — it is the only forget path for a tracked file that fell out of scope
   and was deleted before any reconciliation run (EP4 skips files no longer on disk).
5. **Path-base parity** (invariant I3): `**/`-normalized picomatch patterns match BOTH
   absolute (watcher) and root-relative (batch) paths with the same pattern set via the
   existing `normalizePattern`; no per-EP rewriting.
6. **Entry-gate-only validation** (session ADR-7): the operator-entry `superRefine`
   rejects only a normalized-equal include∩exclude pair (a provably inert entry),
   naming both keys and the pattern. No subsumption solving (not cheaply decidable).
   Cross-key rules never reach the internal config seam (R1 rule).

## Alternatives Considered

- **Generate negated-exclude globs instead of a second field** — operator-invisible
  magic, keeps negation semantics in YAML, no separate validation surface → rejected.
- **Code-shipped per-source-type defaults** — moves the open-ended list into the app
  and cannot express per-source signal sets → rejected.
- **Rely on the content-classifier** — wrong layer (post-read); cannot bound watch cost → rejected.
- **Inline `isPathIncluded && !isPathExcluded` per enforcement point** — four places to
  drift, the exact historical failure class glob-matcher exists to prevent → rejected.
- **A stateful ScopePolicy class** — speculative ceremony → rejected.
- **Derive safe prune-directories from include lists** — real work, unmeasurable benefit
  at these tree sizes; revisit only if descent cost is ever measured → deferred (YAGNI).
- **Warn-log instead of refuse on shadow entries** — operator configs run unattended;
  refusing at parse is the established house answer for inert options → rejected.

## Consequences

Back-compat is exact by construction (field absent ⇒ untouched code paths, pinned by
parse-identity tests). One schema touch means seams cannot drift. New operator-facing
concept documented in `apps/racochu/README.md` + this vault. Reversible: removing the
field restores the old schema; configs using it must be reverted first. Landed as
owner-squashed commit `7464e39`, review-verified at ReviewRound1 (all owned suites green,
e2e include-scope suite proves no watcher blindfold).
