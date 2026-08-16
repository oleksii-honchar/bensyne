---
type: adr
id: ADR-0010
title: "SQLite per Bank for File Metadata Storage"
status: accepted
createdAt: "2026-08-12T00:00:00Z"
updatedAt: "2026-08-12T00:00:00Z"
tags: [storage, sqlite, file-metadata, per-bank]
supersedes: []
superseded_by: []
see_also:
  - "adrs/0005-sqlite-hash-index.adr.md"
  - "concepts/0007-file-metadata-layer.concept.md"
---

# ADR-0010: SQLite per Bank for File Metadata Storage

## Context

The file metadata layer requires relational storage for files, file-chunk relationships, and inter-file relationships. The existing bensyne architecture uses per-bank SQLite databases (mnemosyne.db, hash_index.db) for offline capability and per-bank isolation.

## Decision

Store file metadata in a dedicated SQLite database per memory bank (`file_metadata.db` alongside `mnemosyne.db`), following the existing per-bank SQLite pattern established by the hash index (ADR-0005).

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|--------------|
| **SQLite per bank (chosen)** | Offline, isolated, no deps, follows existing pattern | Limited cross-bank queries | — |
| **PostgreSQL** | Scalable, indexed, cross-bank queries | Requires infrastructure, breaks offline capability | Over-engineered for current scale |
| **Extend mnemosyne.db** | No new DB, co-located | Not ideal for relational queries, couples file metadata to memory storage | Couples concerns |

## Consequences

- **Positive:** Simple management, offline capable, no infrastructure changes, per-bank isolation aligns with existing architecture
- **Negative:** Cross-bank file queries require external orchestration
- **Neutral:** Can migrate to PostgreSQL if scale requires it
