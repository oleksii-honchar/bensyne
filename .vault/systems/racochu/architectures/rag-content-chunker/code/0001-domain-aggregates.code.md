---
type: code
title: "RAG Content Chunker — Domain Entities"
c4_level: code
system: rag-content-chunker
createdAt: "2026-07-31T07:30:00Z"
updatedAt: "2026-07-31T07:30:00Z"
tags: [architecture, domain, ddd]
see_also: ["concepts/0001-chunk-concept.concept.md", "concepts/0002-file-role.concept.md"]
linked_elements: []
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Code: RAG Content Chunker — Domain Entities

## Diagram

```mermaid
C4Code
  title RAG Content Chunker — Domain Entities

  Container(server, "RAG Content Chunker Server", "Node.js + NestJS", "CLI server")

  Boundary(domain, "Domain Layer (src/domain/)", "Boundary") {
    Class_Boundary(chunk, "Chunk", "Entity") {
      Class(chunkId, "id: string", "UUID")
      Class(chunkText, "text: string", "Chunk content")
      Class(chunkIndex, "chunkIndex: number", "Position in sequence")
      Class(totalChunks, "totalChunks: number", "Total chunks from file")
      Class(fileRole, "fileRole: FileRole", "config | code | docs | agent-output")
      Class(importance, "importance: number", "0.0–1.0 importance score")
      Class(tags, "tags: string[]", "Extracted tags (max 20)")
      Class(namespace, "namespace: string", "Mnemosyne namespace for routing")
      Class(metadata, "metadata: Record<string,string>", "filePath, sourceId, etc.")
    }

    Class_Boundary(fileChange, "FileChange", "Aggregate") {
      Class(fcPath, "path: string", "File path")
      Class(fcEvents, "events: DomainEvent[]", "FileAdded/Changed/Deleted events")
    }

    Class_Boundary(watchSource, "WatchSource", "Entity") {
      Class(wsId, "id: string", "Unique source identifier")
      Class(wsPath, "path: string", "Directory to watch")
      Class(wsExclude, "exclude: string[]", "Chokidar ignore patterns")
      Class(wsDebounce, "debounceMs: number", "Debounce interval in ms")
    }
  }

  Boundary(utils, "Shared Utils (src/utils/)", "Boundary") {
    Class(result, "Result<T>", "Success/failure wrapper (no exceptions)")
    Class(errorDetails, "ErrorWithDetails", "Typed error with code + context")
    Class(domainEvent, "DomainEvent", "Base event with timestamp")
  }

  Rel(chunk, result, "Created via Result.ok/ko")
  Rel(fileChange, domainEvent, "Contains typed events")
  Rel(watchSource, result, "Validated via Result pattern")
  Rel(chunk, errorDetails, "Fails with ErrorWithDetails")
```

## Elements

| ID | Name | Type | Description |
|----|------|------|-------------|
| `Chunk` | Chunk Entity | Class | Core domain entity: semantically coherent content fragment with importance, tags, namespace |
| `FileChange` | FileChange Aggregate | Class | Aggregate wrapping file path + typed domain event (Added/Changed/Deleted) |
| `WatchSource` | WatchSource Entity | Class | Configuration entity defining a directory to watch with patterns and debounce |
| `Result<T>` | Result Type | Class | Zero-exception error handling: `Result.ok(value)` or `Result.ko(error)` |
| `ErrorWithDetails` | Error Type | Class | Structured error with message, code, and optional context map |

## Notes

- **Zod validation:** All entities validated via Zod schemas (`chunkEntitySchema`, `watchSourceEntitySchema`, etc.)
- **FileRole enum:** `CONFIG`, `CODE`, `DOCS`, `AGENT_OUTPUT` — drives chunking strategy selection
- **Namespace on Chunk:** Determines which Mnemosyne database the chunk is ingested into (server-side routing)
- **415 unit tests:** Full coverage of entities, use cases, services, infrastructure
