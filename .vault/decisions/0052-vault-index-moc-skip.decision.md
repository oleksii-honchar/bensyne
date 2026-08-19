---
type: decision
id: DEC-0052
system: racochu
title: "Index/MOC Files Fully Skipped for Vault Ingestion"
status: accepted
createdAt: "2026-08-19T18:44:41Z"
updatedAt: "2026-08-19T18:44:41Z"
tags: [chunking, vault, index-files, retrieval]
supersedes: []
superseded_by: []
see_also: [decisions/0051-vault-chunking-strategy.decision.md, concepts/0024-vault-note-chunking.concept.md]
---

# DEC-0052: Index/MOC Files Fully Skipped for Vault Ingestion

## Context

Index files (`_index.md`, `_Vault-Home.md`, `type: index`) are curated link lists, not
content. Embedding them produces low-information vectors that dominate retrieval, but their
links are adjacency records. A navigation chunk per index was considered and rejected:
folder membership is already implicit in file paths (bensyne file ids derive from paths),
and node↔node relations are carried by `see_also` + content wikilinks (empirically
ubiquitous in content nodes).

## Decision

Skip index/MOC files entirely: `Result.ok([])` — **no chunks, no edges**.

Detection: filename (`_index.md` / `_Vault-Home.md`) OR frontmatter `type: index`.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| Tiny navigation chunk per index | Index→member adjacency in graph | One more retrievable link-list vector per folder; adjacency redundant | Redundant with path-derived structure + content edges |
| Ingest as normal docs | Simplest | Link lists pollute retrieval | The feature exists to stop this |

## Consequences

- **Positive:** Zero retrieval noise; matches user expectation ("probably skip").
- **Negative:** Index→member edges never enter the graph (accepted — navigational redundancy).
- **Transitional:** index-file memories already in bensyne persist until the file's next
  change/delete (stale cleanup then forgets them — verified in
  `process-file.use-case.ts`).
