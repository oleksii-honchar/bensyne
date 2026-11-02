---
type: runbook
system: racochu
title: "Startup Persona Edge Reconciliation (self-heal, --skip-edge-reconcile)"
createdAt: "2026-11-02T11:07:00Z"
updatedAt: "2026-11-02T11:07:00Z"
tags: [runbook, personas, edges, startup, racochu, self-heal]
see_also:
  - runbooks/0007-persona-tree-traversal-diagnosis.runbook.md
  - runbooks/0002-production-deployment.runbook.md
---

# Startup Persona Edge Reconciliation

## What it is
`ReprocessEdgesService` (the mechanism previously run only via
`scripts/reprocess-personas.sh` / `scripts/reprocess-edges.sh`) now runs
**automatically** in regular lifecycles, so persona decision trees converge to
materialized `decision_next` edges without an operator step. Inline edge
emission on genuine file changes already happens at processing
(`AgentPersonaChunkingStrategy`); this pass repairs **drift** — DB restores,
pre-feature ingests, ghost edges.

## When it runs (racochu source of truth: `src/main.ts runPersonaEdgeReconcile`)
- plain start / watch: chained **after** startup auto-population, background, never delays the watcher;
- `--resume` / `--force-reprocess` fall-through into watch: background after their pass;
- `--resume --process-only` and `--force-reprocess --process-only`: awaited before exit (queue drained).

## Gates
- Runs only when at least one watch source id matches `^agent-persona_` (same convention as the ops scripts' yq filter); passes the persona-subset only.
- Skipped when the operator passed `--reprocess-edges` (explicit all-sources pass already covers it).
- `--skip-edge-reconcile` suppresses it everywhere (large deployments).
- Failures are logged and **never fatal** (same startup-aux pattern as exclude-reconciliation/TTL).

## Verify it works
```bash
# per persona bank, before/after a start: expansion count (0 → N)
# getPersonaEntryNode → expandFileRelations(entry, decision_next) on agent-persona_<id>
scripts/reprocess-personas.sh            # manual report path still prints file_relations per bank
sqlite3 ../bensyne-mcp/data/banks/persona_<id>/file_metadata.db 'SELECT COUNT(*) FROM file_relations;'
```

## Related drift case
2026-11-02: `agent-persona_worker` had all 10 node files ingested but **0**
`decision_next` relations (entry expansion empty) while a healthy tree expanded
to 19 — same class as [[0007-persona-tree-traversal-diagnosis]] step 5 ("force
reprocess the banks"), which this runbook makes self-repairing at next start.
Note 0007's manual step remains valid; adding a cross-reference there was
surfaced for human decision, not edited automatically.
