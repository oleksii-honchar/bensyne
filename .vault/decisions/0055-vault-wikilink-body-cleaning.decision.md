---
type: decision
id: DEC-0055
system: racochu
title: "Clean Wikilinks from Vault Embedded Body Text"
status: accepted
createdAt: "2026-08-19T18:44:41Z"
updatedAt: "2026-08-19T18:44:41Z"
tags: [chunking, vault, embeddings, wikilinks]
supersedes: []
superseded_by: []
see_also: [decisions/0051-vault-chunking-strategy.decision.md, decisions/0054-vault-wikilink-resolution-ladder.decision.md]
---

# DEC-0055: Clean Wikilinks from Vault Embedded Body Text

## Context

`[[...]]` brackets are noisy embedding tokens; the link *meaning* is already captured as
structured file edges (DEC-0054). Vault grammar uses far more wikilinks in prose than
obsidian sources.

## Decision

Before Mastra chunking, replace `[[target|alias]]` → `alias` and `[[target]]` → `target`
in the body. Edge extraction runs on the **original** body; only the embedding text is
cleaned. Local to the vault strategy (`cleanWikilinksForEmbedding`).

## Alternatives Considered

| Alternative | Why rejected |
|-------------|--------------|
| Leave raw (obsidian behavior) | Noisy tokens; vault prose is wikilink-dense |
| Change obsidian strategy too | Churn beyond scope; obsidian vaults may rely on current embeddings |

## Consequences

- **Positive:** Cleaner embeddings; zero semantic loss (edges carry links).
- **Negative:** Vault/obsidian body handling diverges slightly — accepted:
  source-specific behavior is the point of strategies.
