---
type: memory
title: "SHA-256 Collision Probability is Negligible"
createdAt: "2026-08-07T18:01:00Z"
updatedAt: "2026-08-07T18:01:00Z"
tags: [hash, sha256, deduplication]
see_also:
  - "concepts/0013-file-hash-deduplication.concept.md"
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Memory: SHA-256 Collision Probability is Negligible

## Fact

SHA-256 collision probability is 2^-128 — effectively zero for any practical workload. Hash collisions are ignored in the deduplication design without defensive logic.

## Context

The file hash deduplication feature uses SHA-256 to detect duplicate file content across devices. A collision (two different files producing the same hash) would cause incorrect deduplication — treating different files as the same.

## Impact

No impact. With ~10^6 files, the birthday bound probability is still ~10^-30. The design decision to ignore collisions (ADR-0025) is sound and doesn't require mitigation.
