---
type: decision
id: DEC-0097
title: "Bank Description Backfill via Explicit Operator Script — Not Auto-Seed"
status: accepted
createdAt: "2026-08-28T12:58:00Z"
updatedAt: "2026-08-28T12:58:00Z"
system: bensyne-mcp
tags: [mcp, operator, idempotency, bank-discovery]
supersedes: []
superseded_by: []
see_also:
  - decisions/0095-channel-weighted-keyword-ranking.decision.md
  - runbooks/0008-bank-description-backfill.runbook.md
  - memories/0025-channel-weighting-makes-description-backfill-load-bearing.memory.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# DEC-0097: Bank Description Backfill via Explicit Operator Script — Not Auto-Seed

## Context

Two source banks carry empty descriptions in the production registry
today:

- `agent-sessions` — Racochu-ingested session history (14,113
  memories; highest-traffic bank).
- `vault` — Racochu-ingested vault knowledge from project `.vault/`
  dirs (architecture, ADRs, runbooks).

Under ADR-S12 channel weighting (`description +2`), an empty
description causes each missed query term to lose **2 score points**
(versus 1 under uniform weighting). The backfill becomes
load-bearing for these two banks to surface in search results — see
`memories/0025-channel-weighting-makes-description-backfill-load-bearing`.

## Decision

Ship `apps/bensyne-mcp/scripts/backfill-bank-descriptions.sh` as a
one-shot operator script that calls
`registerMemoryBank(name=..., description=...)` for the two empty banks:

- `agent-sessions` → `"Racochu-ingested session history from ~/.agent-sessions/ — prior decisions, handoffs, session context"`
- `vault` → `"Racochu-ingested vault knowledge from project .vault/ dirs — architecture, ADRs, runbooks"`

**Script rules:**

- Idempotent: each `registerMemoryBank` call overwrites only if
  description is currently empty, OR `--force` is passed.
- Uses the OpenCode runtime's MCP client to call `registerMemoryBank`
  (NOT a Python import — the script runs from a shell, not the MCP
  process).
- Has a `--help` banner; exits non-zero with a clear message if the
  registry is unreachable.
- Refuses to overwrite a non-empty description without `--force`
  (pre-flight check via `listMemoryBanks`).

**Do NOT auto-run on boot.** First run happens manually after the
skill edits ship. Documented in the operator runbook
(`runbooks/0008-bank-description-backfill`).

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|---------------|
| **A. Auto-run on boot via `MemoryBankService.ensure_default_bank` analogue** | Always-current descriptions | Blurs idempotent seed with operator migration; a bad description in the seed propagates silently to every environment; mixes migration-time and runtime code paths | Bad blast radius |
| **B. Bake descriptions into `MemoryBank.of` constants** | No operator step | Descriptions are user-facing and should be reviewable through `registerMemoryBank`, not hardcoded in the aggregate | Wrong layer |
| **C. Defer backfill until v2** | Less v1 work | The backfill is load-bearing under `+2` channel weighting; without it `vault` and `agent-sessions` systematically under-rank for any query term that would have hit their description | R-F risk |

## Consequences

- **Positive:** `vault` and `agent-sessions` become discoverable in
  search results — the load-bearing step for channel-weighted
  ranking.
- **Positive:** Script is idempotent and refuses non-empty overwrites
  without `--force` — safe to run repeatedly.
- **Negative:** No auto-run means operators must remember to run the
  script after `searchMemoryBank` ships. Mitigation: documented in the
  operator runbook; the pre-flight check fails loudly on a re-run if
  either bank is still empty.
- **Negative:** Script-level unit test is out of scope for v1 (ADR-S7
  accepts manual operator verification). P1 follow-up: add a Python
  unit test that mocks `listMemoryBanks` output and exercises the
  pre-flight `--force` / non-empty-overwrite paths.