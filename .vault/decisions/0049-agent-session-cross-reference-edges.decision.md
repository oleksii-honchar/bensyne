---
type: decision
id: DEC-0049
system: racochu
title: "Producer-Side Cross-Reference Content Edges for Agent Sessions"
status: accepted
createdAt: "2026-08-19T13:11:20Z"
updatedAt: "2026-08-19T13:11:20Z"
tags: [agent-sessions, cross-reference, edges, chunking, graph]
supersedes: []
superseded_by: []
see_also: [concepts/0017-agent-session-chunking.concept.md, concepts/0006-file-chunk-relation.concept.md, decisions/0045-wikilink-extraction-graph-structure.decision.md, decisions/0050-session-md-sibling-companion-edges.decision.md]
---

# DEC-0049: Producer-Side Cross-Reference Content Edges for Agent Sessions

## Context

Agent-session files reference one another in their **content** (spec → materials, findings →
materials, plans → findings, archived → current/arbitrary). The strategy previously emitted only
**structural** companion edges (parent_child, sibling) — `content` was available in
`chunkFile` but never scanned, so referenced files never became traversable edges.

Everything downstream already supports `cross_reference` (racoohu DTO passthrough, bensyne
materialization, recall enrichment). Only the **producer-side detection** was missing. The existing
companion detector (single `readdir` + fixed filenames) also could not see **archived** or
**arbitrary** session files.

## Decision

Add a producer-side content scan in `agent-session-chunking.strategy.ts` (`buildCrossReferenceEdges`)
that turns in-content `*.md` references into typed `cross_reference` file edges. Follows the
[[0045-wikilink-extraction-graph-structure]] pattern (absolute `target_path`; bensyne
`derive_file_id` untouched ⇒ no id churn). **No bensyne changes.**

**Detection — two passes, deduped:**
- **Pass 1 (path-pattern, primary):** regex `[\w./~-]+\.md\b`; expand `~`; resolve
  (abs → as-is, rel → vs session root). **No containment guard** — cross-session refs allowed.
  Existence gate: emit only if the target is in the session tree **or** `fs.stat` confirms a real file.
- **Pass 2 (basename, conservative):** distinctive basenames only (under `archive/`, or `session.md`,
  or unique-in-tree); standalone-token match; **collision-skip** on ambiguous basenames.

**Edge contract (ratified in D42):**
- `relation_type = cross_reference` (existing vocabulary, both apps)
- `strength = 0.7` (heuristic content-ref; structural edges stay `1.0`)
- `target_path` = absolute resolved
- **Cross-session references allowed** — the existence gate is the only filter (user ruling 2026-08-19)
- **No dangling** edges (nonexistent refs dropped; self-heal on re-ingest)
- **No self-edges**
- Bounded walk (maxDepth 4, maxFiles 200); on any error → `[]` (chunking always succeeds)

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| Path-pattern (Pass 1) only | Simple | Misses bare-basename / archived-by-name refs | Too narrow |
| Basename (Pass 2) only | Catches by-name refs | Misses path-form refs unless it resolves paths (= Pass 1) | Strictly weaker |
| Emit dangling PENDING stubs for missing refs | Eager edges | Permanent dangling stubs | Existence-gate + re-ingest self-heal is cleaner |
| Match fixed companion filename set only | Fast | Cannot see archived/arbitrary files | Contradicts "any materials file" requirement |
| Implement detection in bensyne | Centralized | Breaks DEC-0045 (id churn) | Producer-side is the established, consistent pattern |
| Session-containment guard (original draft) | Session isolation | Blocks legit cross-session refs | **Removed** per user ruling 2026-08-19 — cross-session refs are a valid use case |

## Consequences

- **Positive:** Agent-session content references become traversable `cross_reference` edges
  (recall → expand → fetch), including archived + arbitrary materials files.
- **Positive:** Cross-session references are intended and positively verified (runbook scenario S9) —
  sessions legitimately reference each other's materials.
- **Negative:** Bounded walk + content scan per `chunkFile` add filesystem I/O (bounded; caching is
  an optional follow-up).
- **Neutral:** No bensyne change, no wire-contract change, no id churn; D41/D40/D39 unaffected.
- **Follow-up:** refresh [[0017-agent-session-chunking]] (this pass) — its flow section was stale
  re: these edges.
