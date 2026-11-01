---
type: decision
id: DEC-0121
system: racochu
title: "No Daemon: Manual CLI-Run Watch with Single-Instance Lock; M3 Treated as Repeat-Cost"
status: accepted
createdAt: "2026-11-01T13:54:35Z"
updatedAt: "2026-11-01T13:54:35Z"
tags: [operations, watch-mode, process-supervision, instance-lock, cli]
supersedes: []
superseded_by: []
see_also:
  - decisions/0119-file-hash-ingest-gate-and-terminal-skip-quarantine.decision.md
  - runbooks/0002-production-deployment.runbook.md
  - runbooks/0003-troubleshooting.runbook.md
  - runbooks/0011-verify-racochu-ingest-gate-holding.runbook.md
  - concepts/0012-processing-model.concept.md
---

# DEC-0121: No Daemon: Manual CLI-Run Watch with Single-Instance Lock; M3 Treated as Repeat-Cost

## Context

racochu had no supervisor (M3): repeated ad-hoc `--resume (all)` / watch starts re-scanned the
whole corpus at *full price* (measured: four `resume (all)` starts within ~4 hours, two only
8 minutes apart; no launch agent on the host). The original design proposal (DEC-A5, 2026-10-31)
was a macOS launchd KeepAlive daemon running watch mode once, plus a watch-mode instance lock.
At user review the operator gave an explicit directive: **"keep watcher runned manually from cli."**

## Decision

1. **No process supervision of any kind** (launchd/KeepAlive, cron, systemd) — explicit non-goal
   of the design. Process supervision in any form was rejected by the operator.
2. **M3 is treated as a repeat-cost problem, not a start-frequency problem:** with the DEC-0119
   gate + skip-rows in place, every repeated manual path is gate-eligible — an unchanged file
   costs one indexed `FileTracker` read + one SHA-256; never-ingestable files short-circuit at
   their skip rows; the only full-price path is the deliberate `--force-reprocess` override. Four
   resume-all starts in an afternoon become four cheap reconciliations: the waste is removed
   without removing the practice.
3. **`autoPopulate` stays ON** — without a daemon it is the sole downtime-recovery path: watcher
   events missed while nothing runs are picked up by the next watch start's auto-populate, which
   the gate now makes economically harmless. (The original "why" for keeping it survives
   daemon-free, a fortiori.)
4. **The watch-mode single-instance lock is kept and gains importance** (it was always the
   strongest part of the original proposal): `data/racochu.watch.lock` acquired exclusively
   (`wx` flag + pid content) by the watch branch in `main.ts` **before** auto-populate; a second
   watcher start exits 1 logging the holder pid (`rg … instance-lock.service.ts`); dead-holder
   stale-pid reclaim once; SIGINT/SIGTERM release. One-shot CLI modes neither take nor honor the
   lock — with no supervisor, overlapping manual starts are the *expected* failure mode and the
   lock is the only guard (it makes the worst overlap — two watchers × auto-populate + live
   events on one SQLite + one bank — impossible).

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|--------------|
| launchd KeepAlive daemon (+ scheduled reconciliation, `.nvmrc`-honoring absolute paths) | Auto-restart, continuous ingestion | Operator explicitly declined supervision ("keep watcher runned manually from cli"); env/path drift risk | Rejected by operator directive at user review 2026-10-31 |
| cron-only `--resume` (E2) | Keeps periodic reconciliation cheap | Loses real-time ingestion the session pipeline depends on | Rejected in original analysis |
| systemd (E3) | Standard Linux supervision | Host family is macOS | Wrong platform |
| No lock | Fewest moving parts | Manual starts as the operating model make overlapping watchers a live risk | The lock is the only guard in a supervisor-less regime; minimal design (pid file, stale-pid reclaim), no dependency |

## Consequences

- **Positive:** the operator keeps full control of process lifetime; the worst concurrent-writer
  overlap becomes impossible; repeated manual starts are cheap **by construction** — their flat
  batch-summary is the acceptance test (see runbook 0011).
- **Negative (user-accepted trade-offs of the directive):** no crash/reboot auto-restart; no live
  ingestion while no process is running. Both were properties of the daemon option only — neither
  is a regression against pre-change behavior.
- **Neutral:** optional cron of `--resume` remains possible for the operator but is *not proposed
  by this design*; deeper SQLite WAL hardening for watch+CLI overlap stays a noted follow-up
  (risk unchanged from today; C6 removes the worst case).
