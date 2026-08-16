---
type: decision
id: DEC-0039
system: racochu
title: "Use File Hash in Metadata for Deduplication"
status: accepted
createdAt: "2026-08-07T18:01:00Z"
updatedAt: "2026-08-07T18:01:00Z"
tags: [deduplication, file-hash, cross-device]
supersedes: []
superseded_by: []
see_also:
  - concepts/0020-file-hash-deduplication.concept.md
  - decisions/0040-native-machine-id-hardware-detection.decision.md
  - specifications/0005-file-hash-deduplication.spec.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# DEC-0039: Use File Hash in Metadata for Deduplication

## Context

Same Obsidian vault synced on multiple devices (e.g., Mac mini, MacBook Pro) — same memory bank, same files, different absolute paths. A file ingested from two devices creates duplicate memories because file paths differ.

## Decision

Use file hash in metadata for deduplication — compute SHA-256 hash of file content in RAG Content Chunker, include in `fileHash` metadata field, and check for existing memories in better-mnemosyne `memory_remember` handler.

**Implementation flow:**
1. Compute SHA-256 hash via `FileHasherService` (Node.js `crypto.createHash('sha256')`)
2. Include `fileHash` in chunk metadata
3. In better-mnemosyne, extract hash from metadata and check `HashIndex`
4. If existing memory found → return `{"status": "deduplicated", "memory_id": ...}`
5. If not found → create new memory, store hash in `HashIndex`

## Alternatives Considered

1. **Path-based deduplication** — paths differ across devices, fundamental mismatch
2. **Semantic search for hash matching** — not deterministic, slow
3. **Source field detection** — less explicit, may misclassify pure memories
4. **Dedicated parameter** — requires API change, breaking change

## Consequences

- **Positive:** Reliable deduplication across devices, no API changes needed, non-breaking for pure memories
- **Negative:** Additional hash computation overhead
- **Mitigation:** SHA-256 is fast; hash failures are non-fatal (log warning, continue)
