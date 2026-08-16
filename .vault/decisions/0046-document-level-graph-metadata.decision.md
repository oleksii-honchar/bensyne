---
type: decision
id: DEC-0046
system: racochu
title: "Document-Level Graph Metadata on All Chunks"
status: accepted
createdAt: "2026-08-08T13:55:00Z"
updatedAt: "2026-08-08T13:55:00Z"
tags: [obsidian, metadata, chunking, document-level]
supersedes: []
superseded_by: []
see_also: [decisions/0044-generic-frontmatter-preservation.decision.md, decisions/0045-wikilink-extraction-graph-structure.decision.md]
---

# DEC-0046: Document-Level Graph Metadata on All Chunks

## Context

`base` (database link) and `wikilinks` (graph edges) describe the whole note, not any single chunk. Per-chunk attachment of per-chunk links would fragment the graph. Consistent with the established enrichment granularity (document-level metadata attached to all chunks).

## Decision

Attach `note.base`, `note.properties.*`, and `note.wikilinks` to **every chunk** produced from the note — frontmatter chunk (importance 0.9) and all body chunks. The metadata is computed once per document and spread uniformly. Wikilinks attached independently of frontmatter presence — body-derived.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| Per-chunk link extraction | Precise locality | Fragments graph; same link repeated | Rejected: retrieval wants the note's full edge set |
| Only on frontmatter chunk | Less duplication | Body chunks lack graph context | Rejected: orphans body chunks from graph |
| All chunks (CHOSEN) | Any chunk retrieves the graph | Duplication across chunks | Accepted: matches `note.*` convention |

## Consequences

- **Positive:** Any retrieved chunk exposes the note's database link and full outlink set.
- **Negative:** Metadata duplicated across chunks (bounded by chunk count).
- **Mitigation:** Consistent with existing `note.*` enrichment behavior; deduped wikilinks keep payload small.
