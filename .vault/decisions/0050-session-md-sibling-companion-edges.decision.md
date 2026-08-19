---
type: decision
id: DEC-0050
system: racochu
title: "Session.md Exposes Sibling Companion Edges"
status: accepted
createdAt: "2026-08-19T13:11:20Z"
updatedAt: "2026-08-19T13:11:20Z"
tags: [agent-sessions, companion-edges, sibling, session-md, chunking]
supersedes: []
superseded_by: []
see_also: [concepts/0017-agent-session-chunking.concept.md, decisions/0049-agent-session-cross-reference-edges.decision.md]
---

# DEC-0050: Session.md Exposes Sibling Companion Edges

## Context

The agent-session chunker (`buildCompanionEdges`) emits `sibling` edges from **every** companion
file — including `session.md` itself. Only `parent_child` is suppressed for the root. Live bank
verification confirmed `session.md` has outgoing `sibling` edges to all present companions.

The D42 runbook initially documented the opposite ("session.md emits no companion edges"),
conflicting with the implemented, pre-existing behavior. The spec itself never stated that claim.

## Decision

`session.md` **does** expose its siblings — session files are conceptually connected in the
agent-session sense, and the sibling edges from the root are semantically correct and
intentionally kept. Align all documentation with the code: runbook/spec assert "no outgoing
`parent_child`; outgoing `sibling` allowed." **No code change** (behavior already correct).

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| Suppress `session.md` sibling edges | Root stays a pure container | Inverts intended connectivity; requires code change | Sessions are conceptually connected |
| Keep the incorrect doc (no edges from root) | No work | Drift from real behavior | Documented behavior must match code |

## Consequences

- **Positive:** Docs, runbook, and concept nodes now correctly describe the root's sibling edges.
- **Neutral:** No behavior change, no migration.
- **Related:** see [[0049-agent-session-cross-reference-edges]] for the content-scan edges added in
  the same round.
