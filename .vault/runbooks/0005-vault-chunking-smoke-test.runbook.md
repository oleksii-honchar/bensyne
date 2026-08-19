---
type: runbook
id: 0005
status: active
createdAt: "2026-08-19T18:44:41Z"
updatedAt: "2026-08-19T18:44:41Z"
system: racochu
tags: [vault, chunking, smoke-test, graph, obsidian]
see_also: [decisions/0051-vault-chunking-strategy.decision.md, decisions/0054-vault-wikilink-resolution-ladder.decision.md, runbooks/0001-graph-smoke-test.runbook.md]
---

# Vault Chunking Smoke Test

## Prerequisites

- A vault directory (any Obsidian vault layout) with:
  - ≥ 3 notes (`.md`), ≥ 1 with wikilinks and ≥ 1 with a frontmatter block.
  - ≥ 1 `_index.md` note (to verify it is skipped).
  - A `.obsidian/` config folder at the vault root.
- Graph DB connection.

## Steps

1. **Ingest** a vault source → expect `file_chunk` + `chunk_content` edges only (no other types).
2. **Resolve a wikilink**: pick a note whose body contains `[[Target]]` and verify:
   - the edge type is `wikilink`;
   - the target note chunk is reachable at depth 1 from the source note chunk.
3. **Verify alias and heading syntax**:
   - `[[Target|Alias]]` → edge type `wikilink:Alias`.
   - `[[Target#Section]]` → edge type `wikilink:#Section`.
4. **Check the 6-level resolution**:
   - Exact match, case-insensitive, any-extension basename, path suffix,
     basename only, and path-suffix match — pick at least 2 notes that hit different
     levels and confirm both resolve.
5. **Check vault note metadata reuse**:
   - Confirm frontmatter is parsed (YAML) and reused, not re-parsed per chunk.
6. **Check `_index.md` skip**:
   - Verify the `_index.md` note has no file node or chunk in the graph.
7. **Check cross-file traversal (if applicable)**:
   - Verify any file referenced in a note is walkable in the bank (all regular files,
     not just `.md`).

## Verification

| Check | Expected |
|-------|----------|
| Vault note has `file_chunk` + `chunk_content` | ✅ |
| `wikilink`, `wikilink:alias`, `wikilink:#h2` edges present | ✅ |
| `![[embed]]` edges are type `wikilink` | ✅ |
| Markdown links are type `mentions` | ✅ |
| `[[wikilinks]]` are NOT type `mentions` | ✅ (regression check) |
| `_index.md` note has no file node | ✅ |
| 6-level ladder resolves across levels | ✅ |
| Cross-file walk reaches non-md files | ✅ (if applicable) |

## Monitoring note

If a note's content changes, re-ingest the vault source and verify the resolution ladder
still matches (no dangling wikilinks). The 8 lint warnings noted in the spec are known
and tracked separately.

## Rollback

Delete the vault source, re-run chunking to remove the vault graph edges, and verify
no residual vault-specific nodes remain in the graph.
