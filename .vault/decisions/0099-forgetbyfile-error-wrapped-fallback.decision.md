---
type: decision
id: DEC-0100
system: racochu
title: "BensyneClient Defensive Fallback for Error-Wrapped FILE_NOT_FOUND"
status: accepted
createdAt: "2026-08-28T17:23:01Z"
updatedAt: "2026-08-28T17:23:01Z"
tags: [racochu, mcp-client, forget, defense-in-depth]
supersedes: []
superseded_by: []
see_also:
  - decisions/0098-forgetfile-file-not-found-json-status.decision.md
  - decisions/0037-continue-on-forget-failure.decision.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# DEC-0100: BensyneClient Defensive Fallback for Error-Wrapped FILE_NOT_FOUND

## Context

Even after the server fix (DEC-0099), a future server regression or an
alternate server could again wrap `FILE_NOT_FOUND` inside a FastMCP error
`text` instead of returning a JSON `status`. The client should not reintroduce
3× retry storms or `ERROR` log spam for a deterministic business state.

See [[0037-continue-on-forget-failure]] for the graceful-degradation
orchestration this decision preserves at the client boundary, and
[[0098-forgetfile-file-not-found-json-status]] for the server-side root-cause
fix this decision complements.

## Decision

In `BensyneClient.forgetByFile`, when `parsed.status` is absent but the parsed
`text` or `error` string contains the literal `FILE_NOT_FOUND`, return
`Result.ok({status: 'FILE_NOT_FOUND'})` immediately (debug-level log), skipping
the retry loop. Defense-in-depth only — the server fix (DEC-0099) is
authoritative; this fallback is for resilience against regressions or
heterogeneous server implementations.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| No client fallback | Minimal code | Any server regression re-introduces the retry storm | Fragile |
| Match any `Error calling tool` text as no-op | Broader coverage | Masks genuine unexpected errors | Too broad |

## Consequences

- **Positive:** belt-and-suspenders; preserves correctness; minimal code;
  genuine unexpected responses still fall through to the warn + retry path.
- **Positive:** paired with DEC-0099, the client recognizes both JSON-status
  and error-wrapped shapes of the `FILE_NOT_FOUND` no-op.
- **Negative:** none material — the fallback triggers only when `status === ''`
  AND the literal `FILE_NOT_FOUND` appears in `text`/`error`.
- **Neutral:** the existing test mock shape `{status:'FILE_NOT_FOUND'}` is
  preserved; a new test asserts the error-wrapped path returns no-op after
  one attempt.
