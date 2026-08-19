---
type: decision
id: DEC-0058
system: racochu
title: "Obsidian Wikilink Edges Existence-Gated — Stubs Restricted to Notes"
status: accepted
createdAt: "2026-08-19T18:44:41Z"
updatedAt: "2026-08-19T18:44:41Z"
tags: [chunking, obsidian, wikilinks, edges, existence-gate]
supersedes: []
superseded_by: []
see_also: [decisions/0045-wikilink-extraction-graph-structure.decision.md, decisions/0035-obsidian-note-chunking-strategy.decision.md, decisions/0057-cross-file-traversal-any-file-targets.decision.md, concepts/0018-obsidian-note-chunking.concept.md]
---

# DEC-0058: Obsidian Wikilink Edges Existence-Gated

## Context

Obsidian emitted every wikilink edge unconditionally (best-effort: bensyne materialized
missing targets as PENDING stubs — intended for forward note refs). Non-md wikilinks
produced **phantom** stubs: `[[diagram.png]]` → stub path `diagram.png.md`, a file that can
never exist. The any-file traversal ruling requires knowing what exists — obsidian must
touch fs.

## Decision

`buildWikilinkEdges` is async and existence-gated (root-anchored, flat protocol preserved):

- **hasExt target** (`path.extname(target) !== ''`) → `resolve(root, target)` as-is:
  exists → real edge; missing → **drop** (kills phantom `*.ext.md` stubs)
- **no-ext target** → `resolve(root, target + '.md')`:
  exists → real edge; missing → **keep** the D4 best-effort stub edge
  (forward note refs still materialize — ratified policy untouched)
- **Self-skip** (new — parity with vault/agent-sessions): self-links emit no edge

## Alternatives Considered

| Alternative | Why rejected |
|-------------|--------------|
| Pure best-effort (no fs) | Leaves the phantom-stub defect for every non-md wikilink — the ruling's core ask stays broken |
| Gate everything, stub nothing | Breaks D4 forward-ref behavior for notes (ratified; existing vaults rely on stubs) |

## Consequences

- **Positive:** No phantom stubs; D4 intent intact; obsidian gains self-edge safety.
- **Negative:** One `stat` per ext target (bounded by wikilink count per file).
- **Transitional:** pre-existing phantom stub rows in bensyne DBs persist until the source
  file's next rebuild (self-heals).
