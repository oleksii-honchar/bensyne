---
type: decision
id: DEC-0014
system: bensyne-mcp
title: "Standalone File Entities (Not Embedded in Memory)"
status: accepted
createdAt: "2026-08-12T00:00:00Z"
updatedAt: "2026-08-12T00:00:00Z"
tags: [domain, entity-design, file-metadata, memory]
supersedes: []
superseded_by: []
see_also:
  - concepts/0002-memory-domain.concept.md
  - concepts/0004-file-metadata-aggregate.concept.md
  - concepts/0006-file-chunk-relation.concept.md
---

# DEC-0014: Standalone File Entities (Not Embedded in Memory)

## Context

File context (path, source type, relationships) needs to be tracked alongside memories (content chunks). The question is whether to embed file fields in the Memory entity or keep file context as standalone entities linked through a FileChunk relationship.

## Decision

Standalone File entities with FileChunk relationship entity. File context is orthogonal to memory semantics; FileChunk acts as the junction between File and Memory.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|--------------|
| **Standalone File (chosen)** | Clean separation, file-level ops, memories exist independently | Extra query for file context | — |
| **Embedded in Memory** | Direct file access | Couples memory to files, pollutes Memory entity | Breaks separation of concerns |
| **Hybrid (file_id in Memory)** | Quick lookup | Still couples memory to files | Partial coupling still problematic |

## Consequences

- **Positive:** Clean domain boundaries, memories can exist independently, enables file-to-file relationships spanning multiple memories
- **Negative:** Additional query to get file context from memory
- **Neutral:** File context only needed for file-related operations
