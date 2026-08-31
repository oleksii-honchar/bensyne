---
type: decision
id: DEC-0103
system: shared
title: "Portable Relative Path as LLM-Facing Persona Node Handle"
status: accepted
createdAt: "2026-08-31T14:57:53Z"
updatedAt: "2026-08-31T14:57:53Z"
tags: [persona, traversal, path-handle, file-tools, racochu, contract]
supersedes: []
superseded_by: []
see_also:
  - decisions/0103-file-ref-resolution-chain.decision.md
  - decisions/0104-path-handle-in-tool-outputs.decision.md
  - decisions/0091-file-tools-file-id-contract.decision.md
  - memories/0027-llm-chimeric-file-id-conflation.memory.md
  - specifications/0009-path-handle-file-reference.spec.md
---

# DEC-0103: Portable Relative Path as LLM-Facing Persona Node Handle

## Context

LLM agents traversing persona decision trees occasionally pass **chimeric file_ids**
to `fetchFile`/`expandFileRelations` (e.g. `file_3cfb…5958` = child[0:13] +
parent[-20:]; both real ids exist in the bank) → `FILE_NOT_FOUND`. Opaque 32-hex
ids are conflation-prone for models (see
[[0027-llm-chimeric-file-id-conflation]]). The read path was proven correct; the
fix is the **addressing surface** the LLM uses.

## Decision

LLM-facing persona node handles are **POSIX-style relative paths from the parent of
the persona tree root**, e.g. `researcher/phase1_framing/130-proceed-on-waive.md`.

- **Producer (racochu, canonical):** `AgentPersonaChunkingStrategy` computes
  `path_handle = relpath(parent(treeRoot), file)` with POSIX separators and emits
  it per chunk in chunk metadata → `BensyneRememberDto.extra` → bensyne
  `files.metadata` (`metadata_json`). No DTO/FileContext/rememberMemory contract
  change — `extra` is the designated extension channel.
- **Consumer fallback (bensyne, legacy rows):** `derive_path_handle(file)` —
  (1) `metadata.path_handle` when present; (2) else substring of the stored path
  after the `/agent-personas/` marker for `source_type: agent-persona`; pure
  string manipulation, no filesystem access (works on puma.lan).
- **Uniqueness:** lookups are bank-scoped (per-bank `file_metadata.db`); persona
  name as first segment prevents cross-persona collisions (verified 18/18 unique
  in `agent-persona_researcher`).
- **No schema migration:** `files.metadata_json` is the sanctioned flexible
  channel (spec 0002 / D28 single-bootstrap policy makes schema changes high-cost;
  DEC-0091 already reads persona flags from the same channel).

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| Hex file_id as-is | None needed | The conflation bug IS the hex-id UX | Rejected by byte-level evidence |
| Short/numeric ids | Shorter tokens | Opaque again; numeric ids collide across banks | Wrong problem layer |
| Big-endian (snowflake) ids | Sortable | ~18–20 digits still spliceable; breaks `derive_file_id(bank,path)` determinism, forces stored map + lookups | Wrong problem layer + contract break |
| Absolute paths | Exact | Machine-specific (racochu Mac paths meaningless on puma.lan); leaks environment | Non-portable |
| New rememberMemory wire field | Explicit | Heavier than needed | `extra` is the designated extension point |

## Consequences

- **Positive:** human-readable, stable, machine-independent handles; models rarely corrupt them; file_id stays the canonical internal key.
- **Negative:** marker derivation couples to the `agent-personas` layout — mitigated by metadata precedence and the racochu producer (canonical since 2026-08-31).
- **Follow-up:** T9 bank-wide re-chunking backfill (canonicalization, not a correctness dependency — suffix matching covers legacy rows).

*Verified 2026-08-31: `path_handle` emitted in `apps/racochu/src/application/strategies/agent-persona-chunking.strategy.ts`; consumed in `apps/bensyne-mcp/src/application/services/file_service.py` (`derive_path_handle`); on `main` at 7c6ae4d; reviewer PASS.*
