---
type: decision
id: DEC-0022
system: racochu
title: "Importance Scoring Algorithm"
status: accepted
createdAt: "2026-07-30T23:00:00Z"
updatedAt: "2026-07-31T07:30:00Z"
tags: [enhancement, importance]
see_also: [concepts/0010-enhancement-pipeline.concept.md]
---

# DEC-0022: Importance Scoring Algorithm

## Context

Need to assign importance scores (0.0–1.0) to memories based on content analysis.

## Decision

Rule-based importance scoring via `ImportanceScoringService` (src/application/services/importance-scoring.service.ts) with configurable factors defined in enhancement config:

- **fileRole** (weight 0.4) — code/config vs prose
- **length** (weight 0.2) — longer = more content
- **keywords** (weight 0.3) — technical terms, domain vocabulary
- **header** (weight 0.1) — presence of section headers

## Alternatives Considered

1. **LLM-based scoring** — Use AI to analyze content importance
2. **Hybrid approach** — Combine rule-based with LLM suggestions
3. **User feedback** — Learn from user interactions

## Consequences

- **Positive**: Fast, consistent, transparent scoring; no external dependencies
- **Negative**: May not capture nuanced content importance
- **Mitigation**: Factors and weights configurable via `enhancement.importance.factors`
