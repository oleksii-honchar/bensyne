---
type: concept
system: racochu
title: "Processing Model"
createdAt: "2026-07-31T07:30:00Z"
updatedAt: "2026-08-07T18:50:00Z"
tags: [domain, processing]
see_also: [concepts/0008-chunk-concept.concept.md, decisions/0036-forget-after-ingest-on-file-update.decision.md, memories/0014-chokidar-macos-dual-events.memory.md]
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
