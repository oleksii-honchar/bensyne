---
type: decision
id: DEC-0107
system: bensyne-mcp
title: "getFileChunks: Instrument Missing Rows, Never Change Behavior"
status: accepted
createdAt: "2026-08-31T14:57:53Z"
updatedAt: "2026-08-31T14:57:53Z"
tags: [recover, mcp-tool, observability, file-chunks, logging]
supersedes: []
superseded_by: []
see_also:
  - decisions/0079-recover-getfilechunks-readonly-tool.decision.md
  - decisions/0082-recover-additive-recovery-change-semantics.decision.md
  - specifications/0007-racochu-recover-mode.spec.md
  - memories/0027-llm-chimeric-file-id-conflation.memory.md
---

# DEC-0107: getFileChunks: Instrument Missing Rows, Never Change Behavior

## Context

The session's "timing/race condition" hypothesis was **refuted** with
byte-level evidence (the root cause was LLM file_id conflation, DEC-0103).
Racochu recover parses `FILE_NOT_FOUND` as a **business state** triggering
idempotent re-ingest — the self-healing path of the pipeline. Any behavior
change risks the recovery pipeline; but a future rows-missing-but-chunks-present
gap must be observable, not invisible.

## Decision

`getFileChunks` handler adds a **WARNING-level structlog log** on a missing file
row: `"getFileChunks: file row not found"` with `memory_bank`, `file_path`,
`derived_file_id`. The response contract (`{"status": "FILE_NOT_FOUND", …}`,
`derive_file_id`) stays **byte-identical** (DEC-0080). No retries, no
pending-state logic — logging only.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| Blind retry on FILE_NOT_FOUND | Might close a race window | ×thousands of files per recover pass; races were refuted | Costs the recovery pipeline for a disproven cause |
| Pending-state handling | Expresses "not yet" | Invents semantics the pipeline doesn't have | Speculative code for a refuted hypothesis |

## Consequences

- **Positive:** any future row-gap becomes production evidence in `bensyne.log`; zero risk to recover idempotency.
- **Negative:** none (additive logging on a cold path).

*Verified 2026-08-31: warning at `apps/bensyne-mcp/src/infrastructure/mcp/handlers.py:508`; contract + no-warning regression reviewer-verified via structlog capture.*
