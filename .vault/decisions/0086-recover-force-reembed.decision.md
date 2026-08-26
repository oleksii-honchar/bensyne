---
type: decision
id: DEC-0087
system: bensyne-mcp
title: "force_reembed Repair Flag on rememberMemory (Stale-Hash-Index Guard)"
status: accepted
createdAt: "2026-08-26T07:18:26Z"
updatedAt: "2026-08-26T07:18:26Z"
tags: [recover, remember-memory, force-reembed, stale-hash-index, repair]
supersedes: []
superseded_by: []
see_also:
  - decisions/0008-sqlite-hash-index.decision.md
  - decisions/0039-file-hash-deduplication-metadata.decision.md
  - decisions/0048-dual-hash-wire-contract.decision.md
  - concepts/0001-hash-index.concept.md
  - concepts/0020-file-hash-deduplication.concept.md
  - specifications/0007-racochu-recover-mode.spec.md
---

# DEC-0087: force_reembed Repair Flag on rememberMemory (Stale-Hash-Index Guard)

## Context

When a memory is lost externally, the `hash_index` still maps `chunk_hash → memory_id`.
Re-submitting that chunk via plain `rememberMemory` hits dedup and returns the **dead** memory id —
the embedding is never re-created. `forgetMemory` cleans hash_index only on its own delete path,
so it cannot fix this state. Recover needs a way to force re-embedding when the dedup target is gone.

## Decision

Add an optional, default-off tool argument `force_reembed: bool` to `rememberMemory`. In
`RememberMemoryUseCase`, only when `force_reembed is True` and a dedup hit's `memory_id` fails
`mnemosyne_client.get` (memory lost):
1. `hash_index_service.remove(memory_id)` — drop the stale entry;
2. remove stale `file_chunks` rows referencing that memory (`get_chunks_by_memory_id` +
   `remove_chunk`) so the dead projection row does not linger with a duplicated `chunk_index`;
3. fall through to the normal miss path: save (embedding) → `hash_index_service.store` →
   `materialize_file_context`.

Live-memory hits and all `force_reembed=False`/absent calls behave exactly as today. The flag is
a tool-level argument (spread by `BensyneClient.remember(chunk, { forceReembed })`), never inside
the v1 metadata contract (DEC-0048 intact). Stale-cleanup uses the same primitives as
`ForgetMemoryUseCase._cleanup_chunks_and_files` but **directly** — never through
`ForgetMemoryUseCase` (its `pure_memories`-only bank guard rejects file banks) and without
`delete_file` on a 0-chunk file (the chunk is immediately re-created by the miss-path materialize).
Verified in code: `remember_memory_use_case.py:62-63`.

## Alternatives Considered

- Separate repair tool that drops stale rows then plain re-submit — rejected for v1: keeps
  `rememberMemory` pristine but adds a second tool + ordering dependency.
- Making `force_reembed` implicit (always check memory on dedup hit) — rejected: adds a point
  read to the hot ingest path for every chunk; opt-in keeps normal pipeline cost unchanged.

## Consequences

- `RememberMemoryUseCase` gains one guarded branch; existing remember/dedup behavior unchanged
  when the flag is absent. New pytest coverage for stale-hit, live-hit, and multi-file re-link.
- Open decision OD-5 resolved as recommended (in-tool flag).
