---
type: concept
system: bensyne-mcp
title: "Materialization"
createdAt: "2026-08-18T07:55:43Z"
updatedAt: "2026-08-18T07:55:43Z"
tags: [domain, file-metadata, projection, remember, idempotency]
see_also:
  - concepts/0004-file-metadata-aggregate.concept.md
  - concepts/0020-file-hash-deduplication.concept.md
  - specifications/0002-file-metadata-layer.spec.md
  - decisions/0048-dual-hash-wire-contract.decision.md
  - decisions/0033-aggregate-repository-service-pattern.decision.md
---

# Concept: Materialization

## What

The file layer is a **projection** (an index) of the memory layer. Content lives in Mnemosyne; the file layer stores only identity (path, `file_hash`, source metadata), links (file → memories via `file_chunks`), and edges (file ↔ file via `file_relations`). *Materialization* is the act of building or refreshing that projection when a memory is remembered — named after the database term **materialized view**: a precomputed derivative of source data, maintained incrementally so readers never recompute it.

## Why

Agents navigate file-centrically — recall is the entry point, then the agent walks `file → edge → file` via `expandFileRelations` / `fetchFile`. That walk is only as good as the projection: precomputed links and edges are what make traversal cheap. Without materialization, every read would re-derive file structure from raw memories.

## Key Details

- **Sole producer: `rememberMemory`.** Materialization runs inside the remember use case (after dedup/save) from the unified chunk contract v1 metadata (`file_path` + edges + hashes). No read tool ever materializes — **reads never write the projection** (write-side invariant). A recalled memory remembered without file context surfaces as `file_enrichment: null` — an honest gap, never retroactive projection.
- **Idempotent upserts.** All mutations go through `FileMetadata` aggregate upserts (`upsert_chunk` / `upsert_relation`) into the single `_persist` chokepoint: equal state → silent no-op (zero events, zero rows) — re-remember of an unchanged file is a no-op by construction.
- **Two hashes, two behaviors (DEC-0048).** `file_hash` changed ⇒ `rebuild_projection` (wipe + re-link); `chunk_hash` dedup hit ⇒ materialize with the *existing* `memory_id` (shared memory links under the new file).
- **Resurrection.** Re-materializing a DELETED file revives it (DELETED → INDEXED, fresh rows) — forget is reversible by re-remember; the projection follows the memory set.
- **Forget is the inverse.** `forgetMemory` removes the memory's chunk rows; a file losing its last chunk becomes a DELETED tombstone (chunks/relations cascade at `_persist`, status-driven).
- **Failure is non-fatal.** A materialization failure never blocks the memory save; the response carries `file_materialization: {status, errors}`; the next remember converges the projection (idempotent).
