---
type: decision
id: DEC-0090
system: racochu
title: "Tilde Expansion in AgentPersonaChunkingStrategy Tree Walk"
status: accepted
createdAt: "2026-08-28T10:58:47Z"
updatedAt: "2026-08-28T10:58:47Z"
tags: [racochu, ingestion, persona, tree-walk, configuration]
supersedes: []
superseded_by: []
see_also:
  - decisions/0090-persona-entry-node-tool.decision.md
  - runbooks/0007-persona-tree-traversal-diagnosis.runbook.md
---

# DEC-0090: Tilde Expansion in AgentPersonaChunkingStrategy Tree Walk

## Context

Bensyne persona agents could not traverse their decision trees: `expandFileRelations`
returned empty `related_files` for every persona bank. Root cause: `racochu.yaml`
declares persona paths with a leading `~`, but `AgentPersonaChunkingStrategy.chunkFile`
did `path.resolve(sourceConfig.path)` on the literal string — `~` treated as a literal
directory → `scandir` ENOENT → `listFilesSafe` returned `[]` →
`buildPersonaDecisionEdges` skipped **every** `decision_next` edge as "dangling" →
`file_relations` stayed empty. The degradation was silent for two days:
`listFilesSafe` never crashes by design, and `logDanglingTargets` early-returns when
`fileIndex.length === 0`, so no per-edge warnings appeared either. Other call sites
(`file-watcher.service.ts`, `force-reprocess.service.ts`) expand `~` correctly — the
strategy alone did not.

## Decision

Expand a leading `~` in `sourceConfig.path` inside the strategy, before resolution:

```ts
// apps/racochu/src/application/strategies/agent-persona-chunking.strategy.ts
const treeRoot = path.resolve(expandHome(sourceConfig.path));

export function expandHome(p: string): string {
  if (p === '~') return os.homedir();
  if (p.startsWith('~/') || p.startsWith('~\\')) return path.join(os.homedir(), p.slice(2));
  return p;
}
```

`expandHome` is a module-level exported helper (unit-tested). Expansion must run
**before** `path.resolve` (resolve turns `~/…` into `/cwd/~/…`).

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| Expand at config load / watcher start (single source of truth) | One place for all call sites | Touches more call sites; the strategy is the ingestion path that matters for edges | Deferred — the three call sites can converge on the shared helper later without behavior change |
| Log a warning on tree-walk failure only | Cheap | Treats the symptom; edges still missing | Rejected alone — combined with the fix instead |

## Consequences

- **Positive:** tree walk succeeds; `decision_next` edges materialize on ingestion; regression test covers `chunkFile` with a `~/…`-relative watchSource path.
- **Negative:** existing persona banks required a one-time re-ingestion — `file_relations` are written only at materialization and chunk dedup is a no-op on re-remember, so the code fix alone did not populate them (done 2026-08-28: 220 relations across 11 banks).
- **Neutral:** `file-watcher.service.ts` / `force-reprocess.service.ts` still have their own expansion (behavior unchanged).

*Verified 2026-08-28: `expandHome` + tests present in `apps/racochu/src/application/strategies/agent-persona-chunking.strategy.ts`.*
