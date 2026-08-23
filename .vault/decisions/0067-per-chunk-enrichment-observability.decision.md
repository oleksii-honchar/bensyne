---
type: decision
id: DEC-0068
system: racochu
title: "Per-Chunk Enrichment Observability — Progress, Failure Position, Aggregate Summary"
status: accepted
createdAt: "2026-08-23T19:20:00Z"
updatedAt: "2026-08-23T20:23:00Z"
tags: [enrichment, observability, logging, force-reprocess, ingest]
supersedes: []
superseded_by: []
see_also: [
  "decisions/0047-disable-enrichment-by-default.decision.md",
  "decisions/0043-non-fatal-enrichment-graceful-degradation.decision.md",
  "decisions/0060-sequential-file-processing.decision.md",
  "concepts/0021-llm-enrichment.concept.md"
]
---

# DEC-0068: Per-Chunk Enrichment Observability (racochu)

## Context

Serial per-chunk enrichment (T9) of large files is blind: no per-chunk logs, and the file-level "Extracted metadata; hasTitle=…" line checks only `docDocs[0]` (mastra-chunking.service.ts:372-387). A 95-chunk file takes ~7 min with zero progress signal; later-chunk failures are invisible. `ForceReprocessService` reprocess/resume loops log per-file results without queue position. Separately, `IngestChunkUseCase` folds `stored` + `deduplicated` into one `success` count (ingest-chunk.use-case.ts:113-115) — operators cannot tell "dedup idle" (correct) from "stuck" during long silent embedding windows.

## Decision

1. **Per-chunk outcome logs** in the serial enrichment loop: INFO `Chunk enriched` (fields: `chunkIndex`, `chunkCount`, `filePath`, `attempts`, `hasTitle`, `hasKeywords`, `hasSummary`) on success; WARN on both-attempts-failed (existing `ExtractMetadata failed`, extended with chunk position + attempts); WARN on 429-exhausted (extended with chunk position). `chunkIndex` is **0-based** to match the domain `chunkIndex` stored by `mapToDomainChunks`; ForceReprocess `[idx/totalFilesInQueue]` is **1-based** (queue position, user notation).
2. **File-level aggregate summary** replaces the first-chunk-only check: INFO `Extracted metadata; enriched=N, failed=F` with `{totalChunks, enrichedCount, failedCount, filePath, hasTitle, hasKeywords, hasSummary}`; WARN `Some chunks failed enrichment` when `failedCount > 0`. `has*` semantics change from first-chunk-only to "present on ≥1 enriched chunk".
3. **`[idx/totalFilesInQueue]`** (1-based) in `ForceReprocessService` per-file processing logs in both `processSource` and `resumeSourceInternal` loops.
4. **Per-file ingest summary breaks out stored/deduplicated/failed** in `IngestChunkUseCase` (replaces single `success` count; per-chunk DEBUG log unchanged). NO dedup behavior change — the 26-min silent-embedding window is correct behavior, now self-explanatory in logs.
5. All logs via existing `BasePinoLogger`; `[mastra-chunking:enrichment]` prefix preserved.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|---|---|---|---|
| **Per-chunk logs (CHOSEN)** | Progress heartbeat + exact failure position; directly answers user ask | INFO volume grows with chunk count | User explicitly wants it for large files |
| Progress heartbeat every Nth chunk | Lower volume | Still blind to exact failure position; more machinery | Rejected |
| Leave first-chunk check as-is | Zero churn | Masks failures (the defect) | Rejected |

## Consequences

- **Positive:** Large-file enrichment is observable: progress per chunk, failure position, aggregate outcome, queue position in reprocess/resume.
- **Positive:** Failures surface in pino (app-level WARN), not only Mastra stderr `console.error`.
- **Positive:** A 26-min zero-embedding window is self-explanatory: ingest summary shows `stored=0 deduplicated=474` (dedup idle, correct) vs a hang.
- **Negative:** Log volume scales with chunk count — accepted, single-line JSON, no PII.
- **Neutral:** External log consumers keying on the old `Extracted metadata; hasTitle=…` line must be aware the fields now mean "≥1 enriched chunk" — message prefix preserved for grep compatibility.
