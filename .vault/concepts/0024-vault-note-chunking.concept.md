---
type: concept
id: 0024
status: active
createdAt: "2026-08-19T18:44:41Z"
updatedAt: "2026-08-19T18:44:41Z"
system: racochu
tags: [chunking, vault, obsidian, wikilinks, graph]
see_also: [decisions/0051-vault-chunking-strategy.decision.md, decisions/0052-vault-index-moc-skip.decision.md, decisions/0054-vault-wikilink-resolution-ladder.decision.md, decisions/0058-obsidian-wikilink-edge-gating.decision.md, concepts/0016-chunking-strategy-pattern.concept.md]
---

# Vault Note Chunking

Vault chunking treats **Obsidian vaults** (`.obsidian/` config folder at the vault root) as a
first-class source via `VaultChunkingStrategy`.

## Rules

| Rule | Behavior |
|------|----------|
| Source detection | `path.hasExt = false` (config folder), `sourceType = vault` |
| Skip | `._index.md` notes (folder MOCs) — index-only, not content (see [0052](../decisions/0052-vault-index-moc-skip.decision.md)) |
| Edge vocabulary | `[[wikilink]]` → `wikilink` (primary), `[[note\|alias]]` → `wikilink:alias`, `[[#h2]]` → `wikilink:#h2`; `![[embed]]` → `wikilink`; markdown links → `mentions`; Obsidian tags → `tags` (see [0053](../decisions/0053-vault-edge-vocabulary-mapping.decision.md)) |
| Resolution | 6-level ladder: exact → case-insensitive → any-ext basename → path suffix → basename → path-suffix (see [0054](../decisions/0054-vault-wikilink-resolution-ladder.decision.md)) |
| Metadata | Frontmatter (YAML) parsed once — same as agent-session; no YAML parser dependency |

## Graph structure

- Body is cleaned (wikilink syntax unwrapped to target text) before chunking.
- Edges: `file_chunk` (vault root → per-note file nodes) → `chunk_content` (file nodes → chunk nodes).

See [0016-chunking-strategy-pattern](0016-chunking-strategy-pattern.concept.md) for the strategy pattern.
