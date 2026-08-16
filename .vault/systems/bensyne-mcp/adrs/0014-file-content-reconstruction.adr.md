---
type: adr
id: ADR-0014
title: "File Content Reconstruction from Chunks with chunk_index Ordering"
status: accepted
createdAt: "2026-08-12T00:00:00Z"
updatedAt: "2026-08-12T00:00:00Z"
tags: [file-metadata, content-reconstruction, chunks, fetchFile]
supersedes: []
superseded_by: []
see_also:
  - "concepts/0006-file-chunk-relation.concept.md"
  - "concepts/0007-file-metadata-layer.concept.md"
---

# ADR-0014: File Content Reconstruction from Chunks with chunk_index Ordering

## Context

When a file is chunked and each chunk is stored as a memory, the original file content needs to be reconstructed from chunks. The question is how to order chunks during reconstruction.

## Decision

Reconstruct from chunks using `chunk_index` ordering (primary) with `startLine`/`endLine` fallback (secondary). File content is NOT stored — only metadata, relationships, and references to memories. Reconstruction happens on-demand.

## Reconstruction Algorithm

1. Retrieve all FileChunk records for file
2. Sort by `chunk_index` (primary), `startLine` (secondary)
3. Retrieve memory content for each chunk
4. Concatenate with gap indicators for missing chunks
5. Return with reconstruction status (`complete` / `partial`)

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|--------------|
| **chunk_index ordering (chosen)** | Accurate, line continuity guaranteed | Requires all chunks | — |
| **Memory creation time** | Simple | Less accurate ordering, unreliable | Creation time doesn't guarantee position |
| **Store full file** | Fast retrieval | Duplicates content in file_metadata.db | Violates "content not stored" constraint |

## Consequences

- **Positive:** Accurate reconstruction, no content duplication, line-accurate positioning
- **Negative:** Requires all chunks for complete reconstruction
- **Neutral:** Partial reconstruction possible with gap indicators
