---
type: decision
id: DEC-0092
system: shared
title: "File Tools Take file_id, Never memory_id"
status: accepted
createdAt: "2026-08-28T10:58:47Z"
updatedAt: "2026-08-31T14:57:53Z"
tags: [contract, mcp-tool, persona, traversal, ids]
supersedes: []
superseded_by: []
see_also:
  - decisions/0103-file-ref-resolution-chain.decision.md
  - decisions/0105-file-not-found-conflation-candidates.decision.md
  - decisions/0090-persona-entry-node-tool.decision.md
  - runbooks/0007-persona-tree-traversal-diagnosis.runbook.md
---

# DEC-0092: File Tools Take file_id, Never memory_id

## Context

The traversal contract conflated two id spaces. `expandFileRelations` validates its
argument as a **file_id** (`expand_file_relations_use_case.py`), but recall results
expose the file id under `file_enrichment.file.id` (not a top-level `file_id`), and the
skills said "memory_id" or were ambiguous. Passing a 16-hex memory id where
`file_<32hex>` is required yields `FILE_NOT_FOUND` — observed in 4+ sessions across
different agents (e.g., case 1's `0f2f59982885ec29` was the architect's entry-node
memory id).

## Decision

Canonical rule: **`expandFileRelations` and `fetchFile` take `file_id` only; memory ids
are never valid for file tools.**

- File id sources: `getPersonaEntryNode` (returns `file_id` explicitly), recall
  results (`file_enrichment.file.id`), `searchFiles` results (`file.id`).
- Skill text updates in `agent-persona-base` (Step 6, Reading Tools) and `bensyne`
  (Phase 4B) state this contract and carry a `FILE_NOT_FOUND` gotcha row.
- 2026-08-31 extension (DEC-0103/DEC-0104): `fetchFile`/`expandFileRelations`
  also accept an explicit `path_handle` reference (at least one of
  `file_id`/`path_handle` required; missing both → `FILE_REF_REQUIRED`).
  `file_id` remains the canonical key — the contract is extended, not masked:
  resolution tries `file_id` first, and `FILE_NOT_FOUND` details now return
  chimera-id candidates (DEC-0106). Skill text teaches `path_handle` as the
  preferred stable reference for persona nodes; memory ids remain never-valid.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| Server-side: accept memory ids, map memory→file via chunks | Agents never get it wrong | Extra mapping logic in every file tool; masks the contract | Skill-text-only fix is simpler and the id distinction is stable |
| Distinct error message for memory-shaped ids | Better diagnostics | Still leaves agents guessing | Noted as possible follow-up; contract taught instead |

## Consequences

- **Positive:** eliminates the recurring `FILE_NOT_FOUND` id-confusion; the contract is documented at every point where an agent obtains a file id.
- **Negative:** none (documentation/contract only — no server behavior change).
- **2026-08-31:** the second observed `FILE_NOT_FOUND` cause (LLM-chimeric
  file_ids, see `memories/0027-llm-chimeric-file-id-conflation.memory.md`) is
  now handled via the explicit `path_handle` channel instead of server-side
  id-sniffing.
