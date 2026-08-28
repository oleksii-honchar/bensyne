---
type: decision
id: DEC-0099
system: bensyne-mcp
title: "forgetFile Returns FILE_NOT_FOUND as JSON Status, Not a Raised Error"
status: accepted
createdAt: "2026-08-28T17:23:01Z"
updatedAt: "2026-08-28T17:23:01Z"
tags: [bensyne-mcp, mcp-contract, forget, idempotency]
supersedes: []
superseded_by: []
see_also:
  - decisions/0036-forget-after-ingest-on-file-update.decision.md
  - decisions/0037-continue-on-forget-failure.decision.md
  - decisions/0079-recover-getfilechunks-readonly-tool.decision.md
  - memories/0026-forgetfile-file-not-found-noop.memory.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# DEC-0099: forgetFile Returns FILE_NOT_FOUND as JSON Status, Not a Raised Error

## Context

Racochu's `BensyneClient.forgetByFile` treats `FILE_NOT_FOUND` as an idempotent
no-op (matching the `already_deleted` and `forgotten` success set), but the
bensyne-mcp `forgetFile` tool raised a `ValidationError` whenever a file row was
missing from the bensyne file DB. FastMCP wrapped the raise into a
`{text: "Error calling tool 'forgetFile': forgetFile failed: FILE_NOT_FOUND — details: {...}"}`
response with no `status` field, so the client's success check
(`status ∈ {forgotten, already_deleted, FILE_NOT_FOUND}`) never matched → 3× retry
storm + `ERROR: Failed to forget file after 3 retries` log spam on every change
or delete event touching a file with no DB row. This was common after the
2026-08-24 mass-forget recovery backfill re-ingested memories without file rows.
`getFileChunks` already returns `{"status": "FILE_NOT_FOUND"}` (handlers.py:505) —
`forgetFile` should match that convention.

See [[0036-forget-after-ingest-on-file-update]], [[0037-continue-on-forget-failure]],
and [[0079-recover-getfilechunks-readonly-tool]] for the prior context this decision
extends.

## Decision

In `ForgetFileUseCase.execute_internal` Step 2, intercept the
`get_file_by_path` `Result.ko` when `errors[0].error_code == 'FILE_NOT_FOUND'`
and return `Result.ok({"status": "FILE_NOT_FOUND"})` instead of propagating.
Keep the `already_deleted` no-op (DELETED tombstones) and `forgotten` success;
keep propagating all other ko (e.g. DB errors). The `file is None` defensive
guard stays untouched — it is effectively unreachable today but guards against
future service changes.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| Client-only fix (parse error-wrapped text as no-op) | Smallest change | Masks the contract mismatch; server stays inconsistent with `getFileChunks`; still fails for other consumers expecting JSON | Treats the symptom, not the root cause |
| Keep raising but teach FastMCP to emit `status` | Uniform error pipeline | Larger change across the error pipeline; no benefit over returning a JSON dict directly | Over-engineered |
| Client always ignores forgetFile errors | Simplest | Loses real error visibility | Dangerous |

## Consequences

- **Positive:** no-op recognized by the existing client success set; retry storm
  stops; log noise removed; aligns with the `getFileChunks` read-only pattern;
  DEC-0037 graceful degradation preserved.
- **Positive:** distinguishes missing-row (`FILE_NOT_FOUND`) from the DELETED
  tombstone facet documented in [[0021-bensyne-forgetfile-tombstone]] and
  detailed in [[0026-forgetfile-file-not-found-noop]].
- **Negative:** a hypothetical consumer relying on catching the error for a
  missing file would see a success no-op — same as any idempotent contract;
  no current consumer does this.
- **Neutral:** `forgetFile` response contract now has three `Result.ok` statuses:
  `forgotten` / `already_deleted` / `FILE_NOT_FOUND`.
