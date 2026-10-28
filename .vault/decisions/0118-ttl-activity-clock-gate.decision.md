---
type: decision
id: DEC-0118
title: "TTL Anti-Re-Ingestion Is a Stateless Activity-Clock Gate (Supersedes the createdAt Clock)"
status: accepted
createdAt: "2026-10-28T18:22:10Z"
updatedAt: "2026-10-28T18:22:10Z"
system: racochu
tags: [ttl, retention, activity-clock, resume, racochu]
supersedes: ["DEC-0075"]
superseded_by: []
see_also:
  - "specifications/0006-source-ttl-sweep.spec.md"
  - "decisions/0073-ttl-sweep-racochu-side.decision.md"
  - "decisions/0074-ttl-clock-filetracker-created-at.decision.md"
  - "decisions/0075-ttl-config-ttl-days.decision.md"
  - "decisions/0076-ttl-sweep-cadence.decision.md"
  - "decisions/0077-ttl-mass-forget-guard.decision.md"
  - "decisions/0078-ttl-tombstone-acceptance.decision.md"
  - "memories/0021-bensyne-forgetfile-tombstone.memory.md"
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# DEC-0118: TTL Anti-Re-Ingestion Is a Stateless Activity-Clock Gate (Supersedes the createdAt Clock)

Implementation status at promotion time: **accepted (owner-confirmed 2026-10-28); implemented in
the working tree at `d2e3797` — uncommitted (committal is a human decision); e2e §7 scenarios
authored, first execution pending host env (review item V1).** Commit the feature and run the
e2e gate before treating the behavior as shipped.

## Context

The TTL sweep ([[0073-ttl-sweep-racochu-side|DEC-0074]] design) hard-deletes the
`FileTracker` row after a successful `forgetFile`, while every batch path
(`racochu --resume`, startup auto-populate via `autoPopulateSources`, `--process-only`)
enumerates **disk** (`force-reprocess.service.ts` `resumeSourceInternal` → `getFiles`).
A forgotten-but-still-on-disk file therefore looked "untracked" and was re-ingested on every
restart — deliberate forgets did not survive restarts. No durable "do not re-ingest" marker
existed anywhere (the bensyne `files` tombstone deliberately resurrects on re-ingest — D21).
The under [[0074-ttl-clock-filetracker-created-at|DEC-0075]] clock (`FileTracker.createdAt`) made
the problem structural: a re-ingested file always got a fresh `createdAt`, so any marker-free
fix left an "accepted legacy wave", and any marker-based fix (this design's first draft —
tombstone columns, ACTIVE-only queries, terminal-op swap, reactivation clock) added permanent
state and a schema change to buy only two stickiness semantics.

## Decision

TTL eligibility becomes a **derived activity fact, never stored state** (session ADR-8 mechanism,
ADR-9 scope decision, owner-confirmed 2026-10-28):

- `pastDue = source.ttlDays is set && now − lastActivity > ttlDays`, evaluated per file at
  decision time. `lastActivity`: file `mtime` (authoritative when present) → row `updatedAt` →
  row `createdAt` fallback for absent files. Strict `>` boundary; `ttlDays` null/≤0 → never.
- One pure helper — `apps/racochu/src/utils/ttl-activity.ts` (`isPastDue`) — is the single home
  of the rule (no I/O; caller stats).
- Exactly **two batch decision points** consume it: (a) the `resumeSourceInternal` loop-top gate
  (covers `--resume` + startup auto-populate + `--process-only`; stats before any
  verify/ingest work; single skip log line); (b) the daily/`--ttl-sweep` expired-set
  derivation, replacing the `findExpiredBySourceId` SQL age clock (method kept,
  deprecation-comment only).
- The gate is a **per-source opt-in** (`ttlDays == null` source enters zero new code paths —
  permanent-material sources like the obsidian bank are intentionally never configured).
- Uniformity (owner-confirmed OD-5): "past due = not eligible for batch paths" applies to
  never-tracked, hard-deleted, and still-tracked files alike. Explicit doors (single-file
  `--force-reprocess`, path-targeted `--recover`, watch `add`/`change`, full/source
  force-reprocess) never consult the gate — intent-expressing paths stay byte-identical.
- `FileTracker.createdAt` demotes to audit-only; **zero schema, config, or API changes**; no
  marker/tombstone machinery (first-draft ADR-1/3/4/5/7 retired).

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|---|---|---|---|
| Stateful racochu-side tombstone (first draft: status column, ACTIVE-only list queries, terminal-op swap, reactivation clock restart) | Stickiness: forgets survive later mtime touches and `ttlDays` removal | Permanent state + schema change + ripple through list queries | Owner flipped OD-4 to gate-only (session record: "it's elegant solution"); activity clock removes the eligibility error itself |
| Resume consults bensyne DELETED rows | Reuses existing durable fact | Capability-proven impossible: `getFileChunks` exposes no file status (DEC-0106 contract); breaks the no-bensyne-changes boundary; needs a D21 policy carve-out | Proven impossible without a bensyne contract change |
| `birthtime`/ctime as clock | — | Not the asked semantics; less reliable cross-platform | Semantics |
| Stored `lastModifiedAt` column synced on ingest (keep SQL age query) | One-query sweep | Drifts for files touched while racochu was down | Stateless derivation cannot drift |
| Accept resurrection | No work | Contradicts the stated user intent | Rejected at framing |
| Seed markers for pre-feature hard-deleted rows | Kills the one-time wave | Needs a nonexistent bensyne by-status read; markers retired anyway | Moot under the gate; bank-visible variant stays a future capability note |

## Consequences

- **Positive:** No re-ingestion of deliberate forgets from the first sweep onward (while files
  stay inactive); idempotent across restarts with zero migration; pre-feature legacy state is
  covered statelessly (no wave in `ttlDays`-configured sources); active files never expire
  prematurely — the [[0006-source-ttl-sweep|Spec-0006]] accepted risk "TTL clock forgets
  actively re-ingested files" is **retired**.
- **Negative (decided trades):** forget durability holds *only while files stay inactive* — a
  real file update re-arms a forgotten file by design (coherent under an activity clock;
  stickiness was consciously traded away, OD-4); mtime trust becomes load-bearing (rsync/backup
  with preserved old mtimes delays re-ingest — benign); verification of past-due-but-still-tracked
  rows defers to the next sweep; per-file `fs.stat` on resume for opted-in sources (negligible).
- **Neutral:** the `ttlDays` config key ([[0075-ttl-config-ttl-days|DEC-0076]]) is unchanged in
  shape but its semantics now read "days since **last activity**" (in-place re-word on that
  node); present-day caveat (review note L1): the absent-file fallback channel in the sweep
  call-site currently supplies `createdAt` only — the full `updatedAt`-aware precedence lives in
  the helper and its tests; wiring `rowUpdatedAt` at the call-site needs a repository/service
  API addition that the change spec forbade.
- **Future path (recorded, not adopted):** cross-device "sticky forget" would need a
  bank-visible capability (bensyne file-status read), not this mechanism.

## Verification

Implemented and reviewer-verified at `d2e3797` (session `review.md` PASS WITH NOTES; reviewer
re-ran scoped suites independently): pure helper `src/utils/ttl-activity.ts` (31 lines: clock
precedence mtime → rowUpdatedAt → rowCreatedAt, strict `>`, opt-in guard); resume gate in
`force-reprocess.service.ts` (import at `:13`, `isPastDue` at `:189` inside the
stat-based activity check ~`:182-195`); sweep derivation in `ttl-reconciliation.service.ts`
(`:10`, `:48`, single clock read `:105`, `isPastDue` `:206`); `findExpiredBySourceId`
deprecation comment `file-memory-tracker.repository.ts:86`; Spec-0006-style e2e extended in
`src/e2e/ttl-sweep/ttl-sweep.test.ts` (9 scenarios numbered §7(1)–(9) 1:1 with the change
spec, plus 3 pre-existing baseline scenarios — first execution pending, review V1); README
"Forget & activity semantics" documented. Vault drift synced same-cycle:
`architectures/racochu/components/0001-server-components.component.md` (ttlSweep wording).
