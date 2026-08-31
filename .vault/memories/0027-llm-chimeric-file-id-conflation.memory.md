---
type: memory
system: shared
title: "LLM Chimeric file_id Conflation Causes FILE_NOT_FOUND"
createdAt: "2026-08-31T14:57:53Z"
updatedAt: "2026-08-31T14:57:53Z"
tags: [persona, traversal, file-tools, gotcha, root-cause]
see_also:
  - decisions/0102-path-handle-portable-relative.decision.md
  - decisions/0105-file-not-found-conflation-candidates.decision.md
  - runbooks/0007-persona-tree-traversal-diagnosis.runbook.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Memory: LLM Chimeric file_id Conflation Causes FILE_NOT_FOUND

## Fact

`FILE_NOT_FOUND` errors during persona-tree traversal are caused by the LLM
**producing chimeric file_ids** — a conflation of two real ids that were both in
its context. Proof case (2026-08-31, `agent-persona_researcher` bank):
`wrong[0:13] == child[0:13]` (intended node `200-check-continuation.md`) and
`wrong[-20:] == parent[-20:]` (the node it came from, `130-proceed-on-waive.md`);
probability by random hash chance ≈ 0. The read path (`fetchFile`,
`getFileChunks`, `derive_file_id`) is correct — a chimera id genuinely does not
exist.

## Context

Investigation of recurring `FILE_NOT_FOUND` for confirmed-ingested files
(session 260831-0915-bensyne-bank-coverage-check). Byte-level verification on
puma.lan ruled out, with evidence: deployed version skew (byte-identical code),
read/write bank/path mismatch, files-table gaps (0 dangling file_ids, 0 missing
memories), memoryBank:'default' hardcoding, and stale/corrupted ids in
`file_relations` (tree stores the correct child id; persona `.md` edges use
paths, not ids).

## Impact

- Drove the path_handle design: portable relative paths as LLM-facing handles,
  hex file_id kept as internal key only (DEC-0103…0106).
- Navigation outputs now hand the LLM `path_handle`/`file_id` verbatim so it
  never reconstructs ids; FILE_NOT_FOUND details return conflation candidates.
- Diagnostic rule for future similar errors: suspect **LLM id reproduction
  drift** before suspecting the storage layer.
