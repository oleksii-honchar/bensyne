---
type: concept
system: racochu
title: "Processing Model"
createdAt: "2026-07-31T07:30:00Z"
updatedAt: "2026-11-01T13:54:35Z"
tags: [domain, processing]
see_also: [concepts/0008-chunk-concept.concept.md, decisions/0036-forget-after-ingest-on-file-update.decision.md, memories/0014-chokidar-macos-dual-events.memory.md, decisions/0119-file-hash-ingest-gate-and-terminal-skip-quarantine.decision.md, decisions/0121-manual-cli-watch-operation-with-instance-lock.decision.md, runbooks/0011-verify-racochu-ingest-gate-holding.runbook.md]
---

# Concept: Processing Model

## What

The Processing Model defines how file changes flow from detection through chunking and ingestion to Mnemosyne — including concurrency, ordering, and fault handling.

## Why

File systems generate events in bursts; Mnemosyne has rate limits. The model ensures controlled, ordered, fault-tolerant processing.

## Key Details

**Flow (verified in src/):**

```
FileWatcherService (chokidar)
    │
    ▼ file:add/change/unlink
AppEventEmitter (@nestjs/event-emitter)
    │
    ▼ @OnEvent FILE_ADDED/CHANGED/DELETED
ProcessFileUseCase
    │
    ├─► handleAdd      → ingestFile (read → chunk → ingest)
    ├─► handleChange    → get old IDs → ingestFile → forget old → per-ID tracker cleanup
    └─► handleDelete    → get IDs → forget all → deleteByFilePath
    │
    ▼ queued via
FileProcessingQueue (bounded async queue)
    │
    ├─► read file content (fs.readFile)
    │
    ├─► ChunkContentUseCase → StrategyRouter → EnhancementPipelineService
    │
    └─► IngestChunkUseCase → MnemosyneClient.remember()
```

**Key properties:**
- **Sequential:** FileProcessingQueue processes files one at a time (no parallel file processing)
- **Debounce:** Configurable per watch source (default 3000ms) — waits for last modification before processing
- **Dedup:** In-memory hash tracking prevents duplicate processing (resets on restart — see memory 0003)
- **Error handling:** Result pattern throughout — errors logged, processing continues for next file
- **Graceful shutdown:** On SIGTERM/SIGINT — stop watchers → drain queue → close Mnemosyne client (30s timeout)
- **Handler separation:** `handleAdd()` (ingest only) vs `handleChange()` (ingest + forget old) vs `handleDelete()` (forget all + clear tracker)
- **Change handling (forget-after-ingest):** `handleChange()` gets old memory IDs, ingests new content, then forgets old memories. Forget failures are non-fatal — new content is always ingested (see DEC-0036, DEC-0037)
- **Delete handling:** `handleDelete()` forgets all tracked memories via MnemosyneClient.forget() and clears the tracker entry
- **Chokidar dedup:** `processing` Set in ProcessFileUseCase skips duplicate events from macOS chokidar (see memory 0007)

---

### Update 2026-11-01 — Content-hash ingest gate, terminal skips, manual operating stance (DEC-0119, DEC-0121)

The processing model gained a **persistent decision layer** in front of ingestion:

- **Ingest gate** in `ProcessFileUseCase` (the class's own comment calls it "the ingest gate
  covering --watch, --process-only, and --resume"): unchanged file hash ⇒ log-and-skip **before
  any destructive step** (`getMemoryIds`/`forgetByFile` in `handleChange` — order-guard
  test-enforced; after the content read in `ingestFile`). Comparison rule copied from DEC-0084
  (skip only when stored hash non-null, computable, equal); **fail-open** on any gate-input
  failure. This supersedes the "in-memory dedup only" era: repeated passes now cost one indexed
  `FileTracker` read + one SHA-256 per unchanged file.
- **Terminal skips:** empty-content / zero-chunk / content-filtered outcomes end the flow with
  `Result.ok` + a quarantined `FileTracker` row (`skipReason`, zero memories) instead of error
  noise or silent no-record — see concept 0014 and DEC-0119.
- **`forceIngest`** parameter carries deliberate corrective intent (force-reprocess, resume
  stale-tracker repair, recover FILE_NOT_FOUND/step-5) past the gate; repair semantics unchanged.
- **Batch observation surface:** every batch path ends with
  `… finished: files=…, gated-skips=…, terminal-skip-skips=…, verified-skips=…, re-ingested=…`
  (health check: runbook 0011).
- **Operating stance (DEC-0121):** no daemon — watch mode is operator-run from the CLI; a second
  watch start is refused by `data/racochu.watch.lock` (holder pid in the message); `autoPopulate`
  stays ON as the only downtime reconciliation, now cheap.
