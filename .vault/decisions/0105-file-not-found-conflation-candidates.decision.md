---
type: decision
id: DEC-0106
system: bensyne-mcp
title: "Chimera-ID Candidates in FILE_NOT_FOUND Details (LLM-Facing Tools Only)"
status: accepted
createdAt: "2026-08-31T14:57:53Z"
updatedAt: "2026-08-31T14:57:53Z"
tags: [persona, traversal, file-tools, error-handling, path-handle]
supersedes: []
superseded_by: []
see_also:
  - memories/0027-llm-chimeric-file-id-conflation.memory.md
  - decisions/0103-file-ref-resolution-chain.decision.md
  - decisions/0098-forgetfile-file-not-found-json-status.decision.md
---

# DEC-0106: Chimera-ID Candidates in FILE_NOT_FOUND Details (LLM-Facing Tools Only)

## Context

Byte-level evidence shows chimeric ids end with the suffix of a real file's id
(the parent node). The intended file is therefore recoverable from the bad id's
tail — letting the agent self-correct in one retry instead of stalling.

## Decision

When `FILE_NOT_FOUND` is returned by `fetchFile`/`expandFileRelations` with an
unresolved `file_id`:

- `details.candidates`: up to 5 files whose stored id matches the file_id's
  trailing 16 hex chars (`FileRepository.find_files_by_id_suffix`), each as
  `{file_id, path, path_handle}`.
- `details.hint`: `"file_id not found — possible id conflation; pick from
  candidates or retry with path_handle"`.
- **Scoped to the two LLM-facing tools.** `getFileChunks` keeps its exact
  machine contract (DEC-0080); JSON-status convention follows DEC-0099.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| Distinct error for memory-shaped ids | Better diagnostics for DEC-0092 cases | Orthogonal problem (memory_id, not file_id) | Can still be added later |
| Auto-resolve the "obvious" candidate | One fewer round-trip | Could return the wrong file silently | Error-with-candidates keeps the agent in the loop |

## Consequences

- **Positive:** one-retry self-correction; the true source of a chimera id surfaces directly.
- **Negative:** tiny extra scan on the error path only.

*Verified 2026-08-31: candidates + hint implemented in `fetch_file_use_case.py`; reviewer real-stack tests confirmed chimera candidates, rescue-by-handle, and hint.*
