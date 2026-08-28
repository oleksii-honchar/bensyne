---
type: decision
id: DEC-0093
system: bensyne-mcp
title: "Recall Bank Scoping via Per-Bank Router Clients"
status: accepted
createdAt: "2026-08-28T10:58:47Z"
updatedAt: "2026-08-28T10:58:47Z"
tags: [bensyne-mcp, recall, memory-bank, router, architecture]
supersedes: []
superseded_by: []
see_also:
  - decisions/0090-persona-entry-node-tool.decision.md
  - runbooks/0007-persona-tree-traversal-diagnosis.runbook.md
---

# DEC-0093: Recall Bank Scoping via Per-Bank Router Clients

## Context

Investigation (RC5) hypothesized that `RecallMemoryUseCase` ignored `memory_bank` — it
reads the param but calls `self.mnemosyne_client.recall(query, limit)` without a bank
argument, so the param looked "documentation-only". ADR-4 proposed forwarding
`memory_bank` to the client. Implementation-time verification (following ADR-4's own
"verify the signature" instruction) traced the real wiring and disproved the premise:

- `handle_recall` (handlers.py) resolves a **bank-bound** client via
  `router.get_instance(memory_bank)` and injects it into the use case.
- `_create_instance` (router.py) builds `MnemosyneClient(memory_bank=…, data_dir=…)` —
  one client, one `<data_dir>/banks/<bank>/mnemosyne.db`.
- `handle_search_files` follows the same pattern.
- The use case's `memory_bank` (default `"default"`) is response/logging metadata, not
  a scoping lever.

A real-storage integration test (`test_recall_bank_scoping_integration.py`, 4/4 green)
proved the isolation: a memory seeded in `persona_researcher` is returned for that bank
and never leaks into `agent-sessions`.

## Decision

- Bank scoping is achieved **by construction** (per-bank router clients). The rule:
  **querying one bank must never search another.**
- **Do NOT** add a `memory_bank` parameter to `MnemosyneClient.recall` — it would be
  dead code on an already bank-bound client.
- Keep `test_recall_bank_scoping_integration.py` as the regression guard (satisfies
  ADR-4's integration-test requirement).
- An empty recall from the "wrong" bank is **correct isolation**, not a bug — the
  persona tree lives in the persona bank, not `agent-sessions`.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| Forward `memory_bank` to `recall()` (original ADR-4) | Matches the hypothesized fix | No-op on bank-bound clients — dead/misleading code | Architecture already scopes upstream |

## Consequences

- **Positive:** no dead code; regression guard proves scoping behavior.
- **Negative:** none.
- **Neutral:** the "memory_bank is ignored" finding was a misreading of the architecture, corrected before any code change landed.
