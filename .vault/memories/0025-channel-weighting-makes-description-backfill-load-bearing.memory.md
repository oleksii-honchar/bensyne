---
type: memory
title: "Channel Weighting Makes Description Backfill Load-Bearing"
createdAt: "2026-08-28T12:58:00Z"
updatedAt: "2026-08-28T12:58:00Z"
system: bensyne-mcp
tags: [mcp, scoring, ranking, load-bearing]
see_also:
  - decisions/0095-channel-weighted-keyword-ranking.decision.md
  - decisions/0096-bank-description-backfill-via-operator-script.decision.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Memory: Channel Weighting Makes Description Backfill Load-Bearing

## Fact

Under channel-weighted keyword ranking (DEC-0096,
`CHANNEL_WEIGHTS = {"name": 1, "description": 2, "derived": 1}`),
the **operator-script bank description backfill**
(`apps/bensyne-mcp/scripts/backfill-bank-descriptions.sh`,
DEC-0097) is **load-bearing**, not a nice-to-have.

## Context

Before ADR-S12 set the description weight to `+2` (uniform `+1` per
channel originally), an empty-description bank would lose **1 score
point** per missed query term. Under channel weighting, the same
missed term costs **2 score points**. For `vault` and `agent-sessions`
— the two highest-traffic banks, both with empty descriptions today —
this means systematic under-ranking for any query term that would have
hit their description.

## Impact

- If operators forget to run `backfill-bank-descriptions.sh` after
  `searchMemoryBank` ships, `vault` and `agent-sessions` will
  systematically under-rank in production search results.
- The backfill script's pre-flight check (refuses to overwrite a
  non-empty description without `--force`) is the **only** runtime
  gate; CI cannot catch this regression because it depends on
  operator action.
- Symptom to watch for: agents calling `searchMemoryBank` for
  project-history or session-history terms and getting only persona
  banks back. Diagnosis: re-run `listMemoryBanks`; if
  `description` is empty for `vault` or `agent-sessions`, the
  backfill didn't run.
- Future channel-weight changes (e.g. raising description to `+3`)
  must re-assess the backfill's load-bearing weight.