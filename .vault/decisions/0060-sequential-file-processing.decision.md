---
type: decision
id: DEC-0060
system: racochu
title: "Sequential File Processing — Remove Double-Queueing in Force-Reprocess"
status: accepted
createdAt: "2026-08-22T15:28:50Z"
updatedAt: "2026-08-22T15:28:50Z"
tags: [file-processing, force-reprocess, queue, deadlock, sequential, regression]
supersedes: []
superseded_by: []
see_also: [concepts/0012-processing-model.concept.md]
---

# DEC-0060: Sequential File Processing — Remove Double-Queueing in Force-Reprocess

## Context

Racoohu runs LLM enrichment on a single compute node; only one enrichment call may run
at a time. CONCEPT-0012 (processing-model) documents the design intent:
"*Sequential:* FileProcessingQueue processes files one at a time (no parallel file
processing)".

The runtime violated this intent: `ForceReprocessService.processSource` wrapped every
file's `execute()` in an outer `FileProcessingQueue.addToQueue` task, while
`ProcessFileUseCase.executeInternal` already enqueues the inner real-work task. The
inner submission executed inside a running queue worker; the single-worker FIFO could
not run it until the outer task finished; the outer task could not finish until the
inner ran. Result: `--force-reprocess` deadlocks the process (reproduced live: frozen,
0% CPU).

All other paths (file watcher, initial ingest) call `execute()` from outside the queue
— the correct pattern — so only force-reprocess deadlocked. The deadlock had no test
coverage: queue tests covered only ordering, length, and FIFO behavior, and the bug
shipped, found only in live operation.

## Decision

Three parts (code- and live-verified 2026-08-22):

1. **Remove the outer queue wrapper (racoohu).** `ForceReprocessService.processSource`
   calls `await this.processFileUseCase.execute(...)` directly in a sequential loop —
   no outer queue wrapper. Serialization is provided solely by
   `executeInternal`'s `addToQueue`, exactly as for the watcher path.

2. **Nested-submission guard in the queue (racoohu).**
   `FileProcessingQueue.addToQueue` throws when called from inside a running queued
   task (detected via `node:async_hooks.AsyncLocalStorage`), so any future double-wrap
   fails loudly at submission instead of deadlocking.

3. **Regression tests (queue-level, in-memory).** Two fast, CI-visible tests lock the
   invariant:
   - guard test: a task that calls `addToQueue` internally receives the thrown error;
     subsequent external submissions succeed;
   - deadlock-reproduction test: a real queue plus an
     `executeInternal`-mimicking consumer (task that submits a nested task) must not
     hang — enforced via test timeout.

## Alternatives Considered

- *Fire-and-forget all `execute()` calls (no await), rely on FIFO* — also sequential,
  but abandons the existing await-based aggregation and defers all synchronization to
  `waitForEmpty()`; weaker error attribution per file. Rejected.
- *Plain boolean flag in the queue instead of AsyncLocalStorage* — a
  `processing === true` check would reject legitimate concurrent outside submissions
  (watcher events during a long task). Only an async-context-scoped flag distinguishes
  "inside a task" from "elsewhere while busy". Rejected.
- *Log-and-continue in the guard (warn, still queue)* — hides the programming error;
  the deadlock would recur silently. Rejected — throw is correct for an invariant
  violation.
- *Rewrite force-reprocess to bypass `execute()` and submit to the queue directly* —
  duplicates the queueing contract in two places; more surface for divergence. Rejected.
- *Integration test at the racochu CLI level (regression coverage)* — slow, requires
  real sources/filesystem; the queue-level test captures the same invariant cheaper.
  Deferred as optional hardening.

## Consequences

- Force-reprocess completes instead of hanging; sequential single-writer LLM processing
  is guaranteed and testable.
- Existing force-reprocess unit tests that asserted the buggy nested-queue contract are
  rewritten to assert direct, sequential `execute` calls.
- The guard slightly changes `addToQueue` semantics: illegal nested submissions throw
  instead of deadlocking — no legitimate caller affected (all call sites audited).
- The double-wrap failure mode becomes a fast, local, CI-visible regression instead of
  a silent production freeze; minimal test-suite overhead (pure in-memory queue tests).
- Follow-up cleanup possible: drop the now-unused queue dependency from
  `ForceReprocessService` (OD-1, deferred).
