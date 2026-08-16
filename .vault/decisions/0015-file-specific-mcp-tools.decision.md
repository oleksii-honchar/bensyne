---
type: decision
id: DEC-0015
system: bensyne-mcp
title: "File-Specific MCP Tools Alongside Memory Tools"
status: accepted
createdAt: "2026-08-12T00:00:00Z"
updatedAt: "2026-08-12T00:00:00Z"
tags: [mcp, tools, file-metadata, api-contract]
supersedes: []
superseded_by: []
see_also:
  - concepts/0007-file-metadata-layer.concept.md
---

# DEC-0015: File-Specific MCP Tools Alongside Memory Tools

## Context

Bensyne needs file-centric operations (search files, reconstruct file content, expand file relations) alongside existing memory-centric operations (recall, remember, forget). The question is whether to rename existing tools or create new file-specific tools.

## Decision

Create new file-specific tools alongside existing memory tools. Existing tools (`recallMemory`, `rememberMemory`, `forgetMemory`) remain for non-file memories. New file tools handle file context.

## Tool Mapping

| Purpose | Tool | Description |
|---------|------|-------------|
| File search | `searchFiles` | Two-phase semantic recall + file metadata enrichment |
| File content | `fetchFile` | Reconstruct file from its chunks |
| Related files | `expandFileRelations` | Get content from related files |
| Non-file recall | `recallMemory` | Semantic recall without file enrichment |
| Non-file remember | `rememberMemory` | Create standalone memory |

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|--------------|
| **New file tools (chosen)** | Clear boundaries, no breaking changes | More tools to maintain | — |
| **Rename existing tools** | Fewer tools | Breaking changes to integrations | Risk of breaking racochu and other consumers |
| **Extend existing tools** | Minimal API changes | Unclear boundaries | File vs memory operations get conflated |

## Consequences

- **Positive:** Backward compatible, clear API boundaries, existing tools can be deprecated later
- **Negative:** More tools to document and maintain
- **Neutral:** Existing tools can be deprecated later if needed
