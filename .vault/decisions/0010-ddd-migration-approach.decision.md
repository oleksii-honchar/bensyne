---
type: decision
id: DEC-0010
system: bensyne-mcp
title: "Python DDD Migration Approach"
status: accepted
createdAt: "2026-08-10T07:00:00Z"
updatedAt: "2026-08-10T07:00:00Z"
tags: [ddd, migration, architecture, python]
supersedes: []
superseded_by: []
see_also:
  - specifications/0001-bensyne-ddd-migration.spec.md
  - architectures/bensyne-mcp/containers/0001-container.container.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# DEC-0010: Python DDD Migration Approach

## Context

bensyne is a multi-tenant namespace-aware MCP server for mnemosyne-oss that had a flat Python architecture with basic domain separation but lacked proper DDD patterns. The architecture had mixed concerns, no rich domain objects, no aggregate pattern, no use case pattern, and no Result pattern for error handling. This made it difficult to maintain and extend for future development.

The decision was made to migrate to DDD. The question was whether to stay in Python or migrate to TypeScript/NestJS to reuse patterns from racochu.

## Decision

**Adopt Python DDD patterns while keeping the Python language stack.** The migration preserves the Python language, adding hexagonal architecture with rich domain objects, use cases, Result pattern, and repository abstraction.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| **Python DDD (chosen)** | Minimal disruption, incremental approach, team familiarity, lower risk | Python type safety weaker than TypeScript, less mature DDD ecosystem | — |
| **Full TypeScript/NestJS Migration** | Direct pattern reuse from racochu, stronger type safety | Complete rewrite risk, high complexity, team skill requirements | Too risky for initial migration |
| **Hybrid Approach (Python + TypeScript)** | Gradual migration, low risk | Two codebases to maintain, inter-service communication overhead | Adds unnecessary complexity |

## Consequences

- **Positive:** Lower migration risk, faster time to market, easier team onboarding, backward compatibility maintained
- **Negative:** Python type safety is weaker than TypeScript, some patterns need custom implementation, less mature DDD ecosystem
- **Neutral:** Team skill set unchanged; future migration to TypeScript still possible
