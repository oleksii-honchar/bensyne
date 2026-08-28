---
type: specification
system: shared
kind: refactor
title: "Fix Racochu forgetByFile FILE_NOT_FOUND Contract Mismatch"
status: completed
createdAt: "2026-08-28T17:23:01Z"
updatedAt: "2026-08-28T17:23:01Z"
owner: ""
target: ""
see_also:
  - decisions/0098-forgetfile-file-not-found-json-status.decision.md
  - decisions/0099-forgetbyfile-error-wrapped-fallback.decision.md
  - decisions/0036-forget-after-ingest-on-file-update.decision.md
  - decisions/0037-continue-on-forget-failure.decision.md
  - decisions/0073-ttl-sweep-racochu-side.decision.md
  - specifications/0006-source-ttl-sweep.spec.md
---

# Specification: Fix Racochu forgetByFile FILE_NOT_FOUND Contract Mismatch

## Goal

Restore the intended idempotent no-op semantics of `forgetFile` for unknown
files at the contract boundary: server returns `{status: 'FILE_NOT_FOUND'}` as a
JSON status (matching `getFileChunks`), client keeps its no-op recognition, and
`ProcessFileUseCase` orchestration stays unchanged (DEC-0037).

## Phases

### Phase 1 — Server fix (SIMPLE, completed)
- `ForgetFileUseCase.execute_internal` Step 2 intercepts the `get_file_by_path`
  ko with `error_code == 'FILE_NOT_FOUND'` → `Result.ok({"status": "FILE_NOT_FOUND"})`.
- Updated pytest (`test_forget_file_use_case.py`) asserts the no-op; added
  `DB_ERROR` guard test; `already_deleted`/`forgotten` paths unchanged.
- See DEC-0099.

### Phase 2 — Client hardening (SIMPLE, completed)
- `BensyneClient.forgetByFile` recognizes error-wrapped `FILE_NOT_FOUND` when
  `status` absent → `Result.ok({status:'FILE_NOT_FOUND'})`, no retry, debug log.
- Jest regression (`bensyne-client.service.test.ts`) asserts `sendRequestMock`
  called once (no retry).
- See DEC-0100.

### Phase 3 — Cross-layer contract verification (completed)
- Integration test `test_forget_file_contract.py` asserts unknown path →
  `status: FILE_NOT_FOUND`, not an error wrapper.

## Behaviors

- `forgetFile` response contract (after fix): `forgotten` / `already_deleted` /
  `FILE_NOT_FOUND` all `Result.ok`.
- Client success set: `forgotten | already_deleted | FILE_NOT_FOUND` (unchanged).
- Change flow (`handleChange`) and delete flow (`handleDelete`) degrade
  gracefully on forget no-op (DEC-0037), no orchestration change.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Server change breaks existing tests expecting `Result.ko(FILE_NOT_FOUND)` | Low | Med | Tests updated; contract is additive in practice |
| Client substring match too broad | Med | Low | Match only literal `'FILE_NOT_FOUND'` in `text`/`error`, not arbitrary error text |
| Log rotation continues to fail after contract fix | High | Med | Tracked separately — out of scope (see Phase 3 / Open Decision #2 in the session spec) |

## Traceability

- Findings: `findings/findings.md` §Root cause Class A, §Verdict, §Recommendations 1–2
- Vault context: DEC-0036, DEC-0037, DEC-0079, DEC-0073 (TTL sweep uses `forgetFile`)
