---
type: decision
id: DEC-0094
system: shared
title: "Load-First Rule Enforced at the System-Prompt Level"
status: accepted
createdAt: "2026-08-28T10:58:47Z"
updatedAt: "2026-08-28T10:58:47Z"
tags: [agents, skills, system-prompt, persona, loading-order]
supersedes: []
superseded_by: []
see_also:
  - decisions/0090-persona-entry-node-tool.decision.md
  - runbooks/0007-persona-tree-traversal-diagnosis.runbook.md
---

# DEC-0094: Load-First Rule Enforced at the System-Prompt Level

## Context

Skills are injected into the system prompt **alphabetically** (better-opencode
`skill/index.ts`), so `agent-persona-base`/`bensyne` are buried among all skills. The
"load agent-persona-base first" rule lived only in persona wrapper prose — which agents
miss: case 3's researcher did all the work and loaded the skills at the END (first
recall at minute 6 of a 6-minute task). A correctly loaded architect in the same session
proved the rule works when followed.

## Decision

Enforce "skills → entry node → current node only" at the system-prompt level, three
layers (cheapest first); **layer 2 was implemented**:

1. **Skill text** — explicit "Load order (MANDATORY)" section at the top of
   `agent-persona-base` (v1.6) and `bensyne` (v1.3): load `agent-persona-base` first,
   then `bensyne`, before any other skill or task work. (Shipped with Task 4.)
2. **Wrapper system prompts** — the load-first rule prepended to all **11**
   bensyne-personas agent prompts (`~/.config/opencode/agents/*.md`, source of truth
   `~/Documents/agent-rules-n-skills/agents/bensyne-personas/`):
   > "Before any other action, load the `agent-persona-base` skill (…STOP-and-flag
   > rule), then the `bensyne` skill (memory MCP usage, bank resolution, recall-first).
   > Then traverse your persona decision tree from the entry node. Recall-first is
   > unconditional."
   Verified 11/11 via `test_task5_system_prompt_load_first.sh`.
3. **Always-apply nudge** (`~/.rules/olho/always-apply/persona-first.mdc`) — optional,
   not implemented.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| Alphabetical sort prefix (`00-` skill names) | Trivial | Fragile against skill-name churn; affects ALL agents, not just bensyne-personas | Rejected |
| Fork change in better-opencode `system.ts` | Centralized | Fork divergence risk; must survive upstream rebases | Not needed — the wrapper layer worked |

## Consequences

- **Positive:** load-first is now in the effective system prompt of every persona agent — impossible to miss, verified by test.
- **Negative:** rule text lives in 11 wrapper files (must be updated in lockstep; catalog parity is test-asserted).
- **Neutral:** blast radius is outside this repo (`agent-rules-n-skills` wrappers) — recorded here because it governs how this system's agents operate. ⚠️ Follow-up flagged in-session: `agents/opencode/` install source is stale (v2.0.x vs live v2.2.x); running `agents.sh install opencode` could regress the prompts.

*Verified 2026-08-28: rule present in all 11 installed agent prompts; catalog parity confirmed by the session's test script.*
