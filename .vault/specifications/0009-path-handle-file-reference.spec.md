---
type: specification
title: "Persona Path Handles + FILE_NOT_FOUND Robustness"
kind: feature
status: active
createdAt: "2026-08-31T14:57:53Z"
updatedAt: "2026-08-31T14:57:53Z"
tags: [persona, traversal, path-handle, file-tools, racochu]
owner: "oleksii"
target: 2026-09-15
see_also:
  - decisions/0102-path-handle-portable-relative.decision.md
  - decisions/0103-file-ref-resolution-chain.decision.md
  - decisions/0104-path-handle-in-tool-outputs.decision.md
  - decisions/0105-file-not-found-conflation-candidates.decision.md
  - decisions/0106-getfilechunks-observability-only.decision.md
  - memories/0027-llm-chimeric-file-id-conflation.memory.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Specification: Persona Path Handles + FILE_NOT_FOUND Robustness

## Goal

Give LLM agents a human-readable, portable, stable reference for persona nodes
(`path_handle`) and make `FILE_NOT_FOUND` self-recoverable — eliminating
chimeric-`file_id` failures — while keeping `file_id` the canonical internal key
(DEC-0092) and the `getFileChunks` machine contract (DEC-0080) byte-identical.

## Phases

### Phase 1 — Core implementation (T1–T8) ✅ completed 2026-08-31

- [x] T1 bensyne: `FileRepository` — `get_file_by_path_handle`, `find_files_by_path_suffix` (LIKE-escaped), `find_files_by_id_suffix`
- [x] T2 bensyne: `FileService.resolve_file_ref` (4-step chain) + `derive_path_handle`
- [x] T3 bensyne: `fetchFile` — `path_handle` param, `FILE_REF_REQUIRED`, response keys, conflation candidates
- [x] T4 bensyne: `expandFileRelations` — same resolution + `path_handle` on source/related files
- [x] T5 bensyne: `getPersonaEntryNode` — `path` + `path_handle` keys (6 → 8)
- [x] T6 bensyne: `getFileChunks` — WARNING log on missing row (response unchanged)
- [x] T7 racochu: `AgentPersonaChunkingStrategy` — emit `path_handle` per chunk (POSIX)
- [x] T8 skills: `agent-persona-base` + `bensyne` document `path_handle` navigation
- Delivered on `main`: baseline `1050fe5` → `7c6ae4d`; reviewer PASS (1984 non-e2e tests + 19/19 independent real-stack suite)

### Phase 2 — Backfill + enrichment (follow-up)

- [ ] T9: bank-wide persona re-chunking to canonicalize `path_handle` metadata (idempotent re-ingest; ~18–21 files per persona; correctness already covered by marker/suffix fallback)
- [ ] Optional: `path_handle` in `recallMemory`/`searchFiles` file_enrichment

## Behaviors

- `fetchFile`/`expandFileRelations` resolve: (1) `file_id` exact → (2) `path_handle` metadata exact → (3) `path_handle` path suffix → else `FILE_NOT_FOUND`.
- A chimeric `file_id` + correct `path_handle` in the same call resolves the real file (the original bug, fixed end-to-end).
- `FILE_NOT_FOUND` from the two LLM-facing tools carries up to 5 conflation candidates `{file_id, path, path_handle}` + a hint.
- Every navigation response exposes `path_handle` (and `fetchFile` also `file_id`) so the LLM never reconstructs ids.
- `getFileChunks` response contract and `derive_file_id` are byte-identical; a WARNING log fires on missing rows.

## Risks

- **LIKE escaping error → wrong file matched** — unit tests with `_`/`%`/`\`; escape order reviewed.
- **Marker derivation couples to `agent-personas` layout** — metadata value takes precedence; T7 is canonical; T9 backfill removes the fallback dependency.
- **FastMCP strict schema rejects the new optional param** — `Annotated[str | None, "…"] = None` pattern (matches existing optionals).
- **Backfill not run** — no functional impact (suffix match covers legacy rows).
- **getFileChunks change affects racochu recover** — no response change; T6 test asserts the contract.

## Milestones

- 2026-08-31: T1–T8 implemented, reviewed (PASS), on `main` (7c6ae4d).
- 2026-09-15 (target): T9 backfill + optional enrichment.

## Links

ADRs: DEC-0103…DEC-0107 (this set); prior: DEC-0080, DEC-0091, DEC-0092.
Memory: 0027 (root cause). Runbook: 0007 (diagnosis, Symptom 2 updated).
Supersedes (session-level): `plans/getFileChunks-bug-solution.md` (disproven version-skew hypothesis).
