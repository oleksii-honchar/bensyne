---
type: decision
id: DEC-0115
title: "Session-Bank Cleanup Regex — Mixed-Case Base62 + Separator Variants"
status: accepted
createdAt: "2026-10-08T20:33:16Z"
updatedAt: "2026-10-08T20:33:16Z"
tags: [bensyne-mcp, session-management, cleanup, naming, regex]
system: bensyne-mcp
supersedes: []
superseded_by: []
see_also:
  - "decisions/0111-ephemeral-session-bank-cleanup.decision.md"
  - "concepts/0027-bank-naming-contract.concept.md"
  - "decisions/0116-session-bank-age-durable-signal.decision.md"
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# DEC-0115: Session-Bank Cleanup Regex — Mixed-Case Base62 + Separator Variants

## Context

The cleanup identification regex from [[0111-ephemeral-session-bank-cleanup]] (`^agent-sessions?-ses_[a-z0-9]+$`) matched **0 of 478** real session banks on puma.lan (live dry-run: `banks_scanned: 587, banks_matched: 0`). Real OpenCode session IDs are mixed-case base62 (e.g. `agent-session-ses_ee35956e4ffeWKu8JTvmReHF0X`), and on-disk banks also use `_` separators (`agent-sessions_ses_*`). A unit test (`test_cleanup_pattern_matching`) baked in the wrong assumption (uppercase must NOT match).

## Decision

Widen the pattern to `^agent-sessions?[-_]ses_[A-Za-z0-9]+$` — case-inclusive character class, both separators. The `ses_` segment stays required, so `agent-sessions_{user_id}` recall banks, `user_*`, `agent-persona_*`, `default` can never match; empty ID (`agent-session-ses_`) does not match (anchored `+`). The test was inverted to assert uppercase and a real production ID DO match.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|---|---|---|---|
| `re.IGNORECASE` on existing pattern | One-token change | Still misses `_`-separator variants; signals "lowercase is the norm" which is false | Half-fix |
| Match any `*ses*` name | Catches every variant incl. `session-ses_*`, bare `ses_*` | Risk of matching non-ephemeral banks; naming contract has no such forms | Too loose for a hard-delete path |
| Prefix-only match `agent-session` | Simple | Would match `agent-sessions_{user_id}` recall banks — durable user context | Breaks naming contract ([[0027-bank-naming-contract]]) |
| Keep variants out of scope | Conservative | Underscore-separator banks would leak forever | `ses_` segment makes them provably session-scoped |

## Consequences

- **Positive:** All real ephemeral banks become visible to cleanup (≈478 on puma).
- **Positive:** Safety gates unchanged: pool-skip, dir-exists, TTL gate, dry-run default.
- **Negative:** Future naming variants need a code update (same caveat as DEC-0111 noted).
- **Neutral:** `pattern` request param remains logging-only, not a filter.
