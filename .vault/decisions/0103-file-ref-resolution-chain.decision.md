---
type: decision
id: DEC-0104
system: bensyne-mcp
title: "file_id-First Resolution Chain with path_handle Fallback"
status: accepted
createdAt: "2026-08-31T14:57:53Z"
updatedAt: "2026-08-31T14:57:53Z"
tags: [persona, traversal, file-tools, path-handle, resolution, contract]
supersedes: []
superseded_by: []
see_also:
  - decisions/0102-path-handle-portable-relative.decision.md
  - decisions/0091-file-tools-file-id-contract.decision.md
  - specifications/0009-path-handle-file-reference.spec.md
---

# DEC-0104: file_id-First Resolution Chain with path_handle Fallback

## Context

Chimeric `file_id`s must self-heal when the LLM also supplies a correct
`path_handle` (DEC-0103), without masking the `file_id` contract
(DEC-0092 rejected server-side silent id-sniffing).

## Decision

`fetchFile` and `expandFileRelations` accept both `file_id` and `path_handle`;
at least one required, else `FILE_REF_REQUIRED` (error details carry both
received values). `FileService.resolve_file_ref(file_id, path_handle)` chain
(per-bank repository, additive — zero behavior change when `file_id` resolves):

1. `file_id` given → exact PK lookup → found: return. *(unique PK: found = correct file)*
2. `path_handle` given → exact metadata match via `json_extract(metadata_json, '$.path_handle')` → return.
3. `path_handle` given → stored-path suffix LIKE match (`_`/`%`/`\` escaped, `ESCAPE '\'`, limit 10) → tie-break: prefer files whose `derive_path_handle(f)` equals the handle, else newest `updated_at`.
4. Else `Ok(None)` → caller returns `FILE_NOT_FOUND` with details (DEC-0106).

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| path_handle first | Self-heal always | Would silently override correct file_ids | Unnecessary — chimera ids never resolve |
| Server-side auto-detection of corrupted file_ids | No new param | DEC-0092 explicitly rejected masking the contract | Fuzzy fallback kept narrow to error details (DEC-0106) |
| Reject chimeric ids with a hard error | Loud | No recovery path for the LLM | Candidates + handle retry is the recovery path |

## Consequences

- **Positive:** 100% of current `file_id` behavior preserved; chimera+handle self-heals in the same call; each step matches on what the caller explicitly supplied.
- **Negative:** leading-wildcard LIKE and `json_extract` queries are non-indexed — negligible at per-bank table size; monitor if banks grow large.
- **Known edge (reviewer INFO):** step 1 swallows a hard repository error and falls through to the handle steps instead of propagating — accepted degradation, optional hardening.

*Verified 2026-08-31: `resolve_file_ref` in `file_service.py`, 3 repository methods in `file_repository.py`, `FILE_REF_REQUIRED` in `fetch_file_use_case.py`; chain + tie-break reviewer-verified with 8/8 independent tests.*
