---
type: decision
id: DEC-0111
title: "Remove Redundant child() Call from BaseUseCase.execute()"
status: accepted
createdAt: "2026-09-27T14:15:00Z"
updatedAt: "2026-09-27T14:15:00Z"
tags: [racochu, logging, base-use-case, singleton, observability]
system: racochu
supersedes: []
superseded_by: []
see_also:
  - "decisions/0009-rotating-file-handler-logging.decision.md"
  - "decisions/0067-per-chunk-enrichment-observability.decision.md"
---

# DEC-0111: Remove Redundant child() Call from BaseUseCase.execute()

## Context

Investigation of the "repeated content logs" issue identified that the `useCase` field was being duplicated hundreds to thousands of times within individual log entries. In a single log file (`racochu.284.log`), 193 out of 1,596 lines contained repeated `useCase` fields, with 218,012 total extra occurrences and a maximum of 2,726 repetitions in a single line (line 147).

The affected use cases were all file processing and chunk ingestion pipeline use cases: `IngestChunkUseCase`, `ProcessFileUseCase`, and `ChunkContentUseCase` — all of which extend `BaseUseCase`.

Root cause: `BaseUseCase` instances are NestJS singletons (`@Injectable()`). The `execute()` method was calling `this.logger = this.logger.child({ useCase: requestName });` on every invocation. Since `child()` creates a logger that inherits all parent bindings and adds new ones, each `execute()` call chained another `useCase` binding. After N executions, the logger had N `useCase` bindings, all of which were serialized into every log entry.

## Decision

Remove the redundant `child()` call from `BaseUseCase.execute()` (line 40 of `src/utils/base-use-case.ts`). The constructor already establishes the `useCase` binding exactly once: `this.logger = this.logger.child({ useCase: this.constructor.name });`. This is the correct place for instance-level logging context.

The fix is minimal (1 line removed) and addresses the root cause directly without architectural changes.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| **Remove redundant child() call (chosen)** | Simplest fix, preserves all behavior, no architectural changes | None identified | — |
| Create fresh child logger per execute() call (local variable) | Enables request-scoped context in future | More invasive, unnecessary complexity, risk of inconsistent logging | Overengineering for current needs |
| Add logger validation to detect duplicate fields | Would catch similar bugs in future | Overhead on every log entry, doesn't fix root cause | Overengineering |

## Consequences

- **Positive:** Eliminates log entry duplication entirely; log file size reduced by ~218,000 extra field occurrences per affected file; JSON parsing reliability improved; debugging complexity reduced.
- **Negative:** None.
- **Neutral:** No API or configuration changes; no impact on DI container behavior.

## Verification

- Fix verified in codebase: `src/utils/base-use-case.ts` line 40 removed.
- Regression test added: `src/utils/base-use-case.test.ts` — "useCase binding not duplicated across multiple execute calls" (lines 157-182).
- Test validates that after 3 consecutive `execute()` calls, the logger still has exactly one `useCase` binding.

## Related

- Logging architecture: [[0009-rotating-file-handler-logging]] (DEC-0009)
- Observability principles: [[0067-per-chunk-enrichment-observability]] (DEC-0067)