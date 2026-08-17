---
type: memory
system: racochu
title: "SHA-256 Collision Probability is Negligible"
createdAt: "2026-08-07T18:01:00Z"
updatedAt: "2026-08-17T11:32:38Z"
tags: [hash, sha256, deduplication]
see_also:
  - concepts/0020-file-hash-deduplication.concept.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Memory: SHA-256 Collision Probability is Negligible

## Fact

SHA-256 collision probability is 2^-128 — effectively zero for any practical workload. Hash collisions are ignored in the deduplication design without defensive logic.

## Context

The file hash deduplication feature uses SHA-256 to detect duplicate file content across devices. A collision (two different files producing the same hash) would cause incorrect deduplication — treating different files as the same. The same argument now applies to the dual-hash wire contract (DEC-0048): `chunk_hash` (SHA-256 of chunk text) is the per-memory dedup key — a collision would conflate two different chunks into one memory.

## Impact

No impact. With ~10^6 files, the birthday bound probability is still ~10^-30. The design decision to ignore collisions (DEC-0039) is sound and doesn't require mitigation. The dedup index is PER-BANK (`data/{memory_bank}/hash_index.db`), so collision exposure for `chunk_hash` is bounded to one bank's chunk population — with ~10^6 chunks, the birthday-bound probability remains ~10^-30. No defensive logic required (DEC-0048).
