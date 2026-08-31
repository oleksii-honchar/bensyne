---
type: decision
id: DEC-0105
system: bensyne-mcp
title: "path_handle Exposed in File-Tool Outputs, Always and Top-Level"
status: accepted
createdAt: "2026-08-31T14:57:53Z"
updatedAt: "2026-08-31T14:57:53Z"
tags: [persona, traversal, mcp-tool, path-handle, contract]
supersedes: []
superseded_by: []
see_also:
  - decisions/0090-persona-entry-node-tool.decision.md
  - decisions/0102-path-handle-portable-relative.decision.md
  - runbooks/0007-persona-tree-traversal-diagnosis.runbook.md
---

# DEC-0105: path_handle Exposed in File-Tool Outputs, Always and Top-Level

## Context

Persona navigation is iterative: every response must hand the LLM the reference
for the next call. The LLM must never have to compute a relative path itself
(it is unreliable at that) — and must never reconstruct a 32-hex id from memory
(DEC-0103 root cause).

## Decision

Handles are exposed unconditionally (not gated on `include_metadata`):

- **`getPersonaEntryNode`** — response contract extended 6 → 8 keys: adds
  `path` (stored absolute path) and `path_handle` (via `derive_path_handle`).
- **`fetchFile`** — success response adds top-level `file_id` and `path_handle`.
- **`expandFileRelations`** — adds `path_handle` to the `source_file` dict and
  to each `related_files[].file` dict (computed on the underlying `File`;
  `File.to_dict()` itself unchanged).

Skills (`agent-persona-base`, `bensyne`) were updated the same day: navigation
guidance prefers `path_handle` for persona nodes; `FILE_NOT_FOUND` gotcha now
includes the conflation-candidates recovery path.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| Gate handles behind include_metadata | Smaller default payload | Handles become opt-in; starves the traversal loop | LLM needs them on every step |
| Let the LLM derive relative paths | No server change | LLMs are unreliable at relpath math | Produces the same class of bug |

## Consequences

- **Positive:** every navigation response carries the stable reference for the next call; closed loop (entry node → edge → node → edge …).
- **Negative:** slightly larger tool payloads; new response keys are additive (consumers unaffected).

*Verified 2026-08-31: `get_persona_entry_node_use_case.py`, `fetch_file_use_case.py`, `expand_file_relations_use_case.py` on `main` at 7c6ae4d; installed skill copies in `~/.agents/skills/` contain path_handle guidance.*
