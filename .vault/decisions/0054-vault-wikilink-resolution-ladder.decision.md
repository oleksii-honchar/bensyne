---
type: decision
id: DEC-0054
system: racochu
title: "Vault-Aware Wikilink Resolution Ladder with Existence Gate"
status: accepted
createdAt: "2026-08-19T18:44:41Z"
updatedAt: "2026-08-19T18:44:41Z"
tags: [chunking, vault, wikilinks, resolution, edges]
supersedes: []
superseded_by: []
see_also: [decisions/0045-wikilink-extraction-graph-structure.decision.md, decisions/0049-agent-session-cross-reference-edges.decision.md, decisions/0057-cross-file-traversal-any-file-targets.decision.md, concepts/0024-vault-note-chunking.concept.md]
---

# DEC-0054: Vault-Aware Wikilink Resolution Ladder with Existence Gate

## Context

Vault wikilinks appear in two forms: path form (`[[concepts/0021-x.concept]]` — naive join
works) and bare form (`[[0045-x]]` — naive `root + target + '.md'` breaks; target is in a
subfolder). Precedents conflicted: obsidian emits best-effort stubs; the ratified edge
contract (DEC-0049) existence-gates and drops missing targets.

**Amendment (2026-08-19, post-review user ruling):** any in-bank file reference must be
traversable regardless of extension (attachments like `[[diagram.png]]` are a real Obsidian
pattern). Resolution became **notes-first, any-file**: note protocol first (backward
compatible), then same-name files of any type. Walk bounds kept (4/200, 5/500) now counting
all files. See [[0057-cross-file-traversal-any-file-targets]].

## Decision

`resolveWikilinkTarget` ladder — deterministic, **first existing candidate wins**:

1. **Path form** (target contains `/`) — terminal:
   - ext target → `resolve(vaultRoot, target)` as-is (fixes the `toMd()` bug:
     `[[assets/diagram.png]]` no longer becomes `assets/diagram.png.md`)
   - no-ext target → `resolve(vaultRoot, target + '.md')`
   - both candidates `fs.stat`-gated
2. **Bare form** ladder:
   - **a.** `resolve(vaultRoot, target + '.md')` — root-level note
   - **b.** `resolve(dirname(filePath), target + '.md')` — same-folder note
   - **c.** `resolve(vaultRoot, target)` — root-level **as-is** (extensionless
     `[[Makefile]]`, explicit-ext targets)
   - **d.** `resolve(dirname(filePath), target)` — same-folder **as-is**
   - **e.** Vault-wide walk over **ALL files** (lazy — only when a–d miss),
     bounded (maxDepth 5, maxFiles 500, counts all files):
     - match: `basename === t` OR `stem(basename) === t` OR `stem(basename).startsWith(t + '.')`
       (typed-node rule: `[[0045-x]]` → `decisions/0045-x.decision.md`)
     - `stem` = basename with last extension removed
     - exactly 1 match → use; 0 or >1 (ambiguous) → drop; early-exit at 2 matches
3. **Existence gate + self-skip** on every emitted candidate; fs errors → drop.

Backward compatible by construction: steps a–b and the typed-node rule are unchanged from
the original design; c/d/e are append-only additions.

## Alternatives Considered

| Alternative | Why rejected |
|-------------|--------------|
| Obsidian-style best-effort stubs | DEC-0049's existence gate is the newer ratified contract; vault is a closed grammar — unresolvable names are authoring errors, not forward refs; re-ingest self-heals |
| Fully file-scoped wikilinks (drop note protocol) | Regression-sensitive: `[[0045-x]]` could change winner if a same-name non-md file appears; inverts established semantics |
| Eager full-vault index cache | Stale index could emit dangling edges; invalidation machinery over-engineered at current vault sizes (follow-up candidate) |
| Raise walk bounds | No observed misses; walks are lazy + early-exit; revisit with evidence |

## Consequences

- **Positive:** Correct resolution for both empirical link forms; attachment + extensionless
  files now reachable; no dangling edges; deterministic.
- **Negative:** Up to 2 extra cheap `stat` calls per bare link before the lazy walk; the
  500-file cap may truncate before a deep match in image-heavy vaults (tracked).
