---
type: decision
id: DEC-0114
system: bensyne-mcp
title: "Update verify-source-consistency.mjs for BEAM Architecture"
status: accepted
createdAt: "2026-09-28T18:47:00Z"
updatedAt: "2026-09-28T18:47:00Z"
tags: [verification, beam-architecture, episodic-memory, file-chunks, consistency]
supersedes: []
superseded_by: []
see_also:
  - decisions/0109-episodic-memory-tier-migration.decision.md
  - decisions/0112-use-client-side-remember-episodic.decision.md
  - decisions/0113-file-chunks-reingest-index-fix.decision.md
---

# DEC-0114: Update verify-source-consistency.mjs for BEAM Architecture

## Context

The `verify-source-consistency.mjs` script was checking the legacy `memories` table for consistency, which was never populated in the BEAM (Working/Episodic/Scratchpad) architecture. This led to confusion: the script reported the `memories` table as "skipped," making it appear that memories were being lost.

The `memories` table is legacy — it was the original storage mechanism before the BEAM architecture. The library's `remember()` method dual-writes to the legacy `memories` table for backward compatibility, but bensyne's direct episodic inserts bypass this.

## Decision

Update `verify-source-consistency.mjs` to validate the actual BEAM architecture:
- Check `episodic_memory` directly for agent-session and persona entries (not the legacy `memories` table)
- Verify `file_chunks` index integrity for file-backed memories
- Detect orphaned `file_chunks` entries (no corresponding episodic memory)
- Detect missing index entries (episodic memories without `file_chunks` links)
- Check FTS coverage for recall quality

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|---|---|---|---|
| Keep outdated checks | No change | Misleading results; not useful for BEAM | Script should validate the actual architecture |
| Create separate BEAM verification script | Preserves legacy script | Two scripts to maintain | Updating existing script is simpler |
| Deprecate the script entirely | Simple | Lose diagnostic capability | Script can be made useful with updates |
| Add memory table write-back | Makes old checks pass | Defeats purpose of BEAM architecture | Update the checks instead |

## Consequences

- **Positive:** Script becomes a useful diagnostic tool for the actual BEAM architecture; catches `file_chunks` index inconsistencies that cause the "disappearance" issue; detects orphaned chunks and missing index entries; validates FTS coverage.
- **Negative:** Legacy `memories` table is no longer verified (acceptable since it's write-only for backward compatibility).
- **Neutral:** Script remains in `apps/racochu/scripts/` — same location, updated checks.

## Verification

- Manual testing: script correctly identifies episodic entries, file_chunks integrity issues, orphaned chunks, and missing index entries
- Script output matches actual database state
- No false positives or false negatives in tested scenarios