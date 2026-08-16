---
type: adr
id: ADR-0004
title: "Namespace Enforcement — Breaking Change Strategy"
status: accepted
createdAt: "2026-08-01T12:00:00Z"
updatedAt: "2026-08-01T12:00:00Z"
tags: [namespace, migration]
see_also: ["adrs/0002-namespace-parameter-enforcement.adr.md"]
---

# ADR-0004: Namespace Enforcement — Breaking Change Strategy

## Context
Making namespace required is a breaking change for existing clients that don't send namespace parameter.

## Decision
Implement hard enforcement immediately — clients without namespace parameter receive `ValidationError`.

## Rationale
1. **Safety first** — Risk of cross-namespace contamination outweighs migration cost
2. **Small client base** — Only RAG Content Chunker and manual CLI users
3. **Clear error message** — "namespace parameter is required" is self-documenting
4. **No legacy debt** — Don't burden future with deprecated soft enforcement

## Alternatives Considered
1. **Deprecation period** — Log warnings for N weeks, then enforce — adds complexity
2. **Feature flag** — Toggle enforcement on/off — operational burden
3. **Gradual rollout** — Enforce per-tool over time — inconsistent

## Consequences
- **Positive**: Clean migration, no legacy code
- **Negative**: Existing clients must be updated
- **Mitigation**: Update RAG Content Chunker in same release window
