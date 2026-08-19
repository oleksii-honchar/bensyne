---
type: decision
id: DEC-0057
system: racochu
title: "Cross-File Traversal — Any File Target, Per-Strategy Resolution Ladders"
status: accepted
createdAt: "2026-08-19T18:44:41Z"
updatedAt: "2026-08-19T18:44:41Z"
tags: [chunking, edges, traversal, any-file, cross-file]
supersedes: []
superseded_by: []
see_also: [decisions/0049-agent-session-cross-reference-edges.decision.md, decisions/0054-vault-wikilink-resolution-ladder.decision.md, decisions/0058-obsidian-wikilink-edge-gating.decision.md]
---

# DEC-0057: Cross-File Traversal — Any File Target, Per-Strategy Ladders

## Context

Post-review user ruling (2026-08-19, verbatim): "We should allow any file cross reference
and traversal. Whatever source file references another file in bank — it should be
traversable." Two cross-cutting questions: (Q3) may edges target binary/attachment files?
(Q6) should reference extraction be unified across strategies?

## Decision

**Q3 — Any file on disk.** No extension/type filtering anywhere in resolution. Edges are
metadata: strategies only `fs.stat` the target, never read its content (content reading
is the watcher's separate concern). If a verified file exists at the resolved path, the
edge may target it.

**Q6 — Per-strategy ladders, no forced shared abstraction.** Each strategy owns its
resolution code. The three protocols genuinely differ:

- **agent-sessions** resolves *prose path tokens* (regex-driven, two-pass, pool + stat)
- **vault** resolves *wikilinks* (deterministic ladder, lazy early-exit BFS)
- **obsidian** resolves *wikilinks* (flat root join + stub policy)

A common abstraction would parameterize away the semantics that make each correct.
`extractWikilinks` (the one truly shared extractor) is already extension-agnostic.

## Alternatives Considered

| Alternative | Why rejected |
|-------------|--------------|
| Text-like + known attachment types | Ad-hoc list to maintain; blocks legitimate targets (`.sqlite`, `.bin` fixtures) |
| Allowlist | Same problems, stricter; contradicts "any file" ruling |
| Shared token regex + shared walk util | Forces loosest protocol into strictest (or vice versa); two walk shapes don't share cleanly; premature abstraction (violates "no unnecessary ports") |

## Consequences

- **Positive:** Dead-simple, ruling-aligned; zero read-path risk (stat only); localized,
  independently testable amendments.
- **Negative:** Slight duplication of trivial stat-check helpers (pre-existing pattern, accepted).
- **Ratified trade-off:** reference tokens can resolve outside the source root (existence-
  gated, stat-only, no content exposure at resolution time) — pre-existing design, carried
  forward by the ruling.
