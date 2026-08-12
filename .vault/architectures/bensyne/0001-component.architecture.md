---
type: component
title: "Bensyne — Component Level (Hexagonal Layers)"
c4_level: component
system: bensyne
createdAt: "2026-08-11T00:00:00Z"
updatedAt: "2026-08-12T16:44:16Z"
tags: [component, architecture, hexagonal]
see_also:
  - "architectures/bensyne/0001-container.architecture.md"
  - "architectures/bensyne/0002-file-metadata.code.md"
  - "concepts/0003-memory-bank-aggregate.concept.md"
  - "concepts/0002-memory-domain.concept.md"
  - "specifications/0001-bensyne-ddd-migration.spec.md"
linked_elements:
  - mcp-server
  - use-cases
  - memory-bank-aggregate
  - memory-bank-entity
  - memory-entity
  - file-hash-vo
  - file-metadata-aggregate
  - file-entity
  - file-chunk-entity
  - file-relation-entity
  - file-service
  - mnemosyne-client
  - hash-index-service
  - file-metadata-connection
  - result-pattern
---

# Bensyne — Component Level (Hexagonal Layers)

## Diagram

```mermaid
flowchart TB
    subgraph Adapters["◇ Adapters"]
        MCP["FastMCP Server\nMCP protocol entry point — routes 11 tool calls to use cases"]
    end

    subgraph Application["◇ Application"]
        UC["Use Cases\nRememberMemory · RecallMemory · ForgetMemory · UpdateMemory\nSleep · ListBanks · RegisterBank · SearchFiles\nExpandFileRelations · FetchFile"]
        FS["FileService\nAggregate-based orchestration for file metadata\ncreate/update/delete file · link_chunk · create_relation · get_file"]
    end

    subgraph Domain["◇ Domain"]
        MBA["MemoryBankAggregate\nAggregate root — remember · forget · activate · suspend\nProduces domain events in Result.events"]
        MB["MemoryBank Entity\nname · description · status\n(active/registered/suspended) · memory_count"]
        MEM["Memory Entity\ncontent · importance · scope · source\nveracity · metadata"]
        FH["FileHash Value Object\nSHA-256 hash_value (64 hex chars)"]
        FMA["FileMetadataAggregate\nAggregate root — file · chunks · relations\nadd_chunk/remove_chunk/add_relation · compose_content"]
        FE["File Entity\nid · path · source_type · hash · file_type\nsize · language · status · summary\naggregated_keywords/tags"]
        FCE["FileChunk Entity\nid · file_id · memory_id · chunk_index\nstart_line/end_line · content_hash\ncontent_type · is_partial"]
        FRE["FileRelation Entity\nid · source_file_id · target_file_id\nrelation_type · strength · direction · description"]
    end

    subgraph Infrastructure["◇ Infrastructure"]
        MC["MnemosyneClient\nWraps mnemosyne-oss with Result[T]\nremember · recall · forget · update · sleep · stats"]
        HIS["HashIndexService\nWraps HashIndex with Result[T]\nstore · lookup · remove"]
        FMC["FileMetadataConnectionManager\nPer-bank SQLite conn pool · WAL · migrations V1–V5"]
        FR["FileRepository (SQLAlchemy ORM)\nsave/get/list · FTS5 search · merge() upsert"]
        FCR["FileChunkRepository (SQLAlchemy ORM)\nsave/get by file · get by memory"]
        FRR["FileRelationRepository (SQLAlchemy ORM)\nsave/get by file · filter by type"]
    end

    MNEM["mnemosyne-oss Library\nExternal memory engine\n(lazy-imported)"]:::ext
    HDB[("HashIndex SQLite DB\nWAL-mode file hash index")]:::db
    FDB[("file_metadata.db\nfiles · file_chunks · file_relations · FTS5")]:::db

    MCP -->|"Dispatches tool calls"| UC
    UC -->|"Orchestrates file ops"| FS
    UC -->|"Operates on aggregate"| MBA
    MBA -->|"Composes"| MB
    MBA -->|"Composes List[Memory]"| MEM
    FS -->|"Loads/saves aggregate"| FMA
    FMA -->|"Composes"| FE
    FMA -->|"Composes List[FileChunk]"| FCE
    FMA -->|"Composes List[FileRelation]"| FRE
    UC -->|"Dedup lookup/store"| HIS
    UC -->|"Persist memories"| MC
    MC -->|"Library calls"| MNEM
    HIS -->|"WAL-mode R/W"| HDB
    FS -->|"Sessions + ORM"| FMC
    FMC -->|"Engine/Session"| FR
    FMC -->|"Engine/Session"| FCR
    FMC -->|"Engine/Session"| FRR
    FR -->|"Reads/writes"| FDB
    FCR -->|"Reads/writes"| FDB
    FRR -->|"Reads/writes"| FDB

    classDef ext fill:#f9f2f4,stroke:#d14d72,stroke-width:2px
    classDef db fill:#e8f8f5,stroke:#1abc9c,stroke-width:2px
```

## Elements

| ID | Name | Type | Technology | Description |
|----|------|------|-----------|-------------|
| mcp-server | FastMCP Server | Component | FastMCP | MCP protocol entry point — routes tool calls to use cases |
| use-cases | Use Cases | Component | Python | 10 use cases: RememberMemory, RecallMemory, ForgetMemory, UpdateMemory, Sleep, ListBanks, RegisterBank, SearchFiles, ExpandFileRelations, FetchFile |
| file-service | FileService | Component | Python | Application service — aggregate-based orchestration for file CRUD, chunk linking, relations |
| memory-bank-aggregate | MemoryBankAggregate | Component | Python/frozen dataclass | Aggregate root — orchestrates MemoryBank + List[Memory] |
| memory-bank-entity | MemoryBank Entity | Component | Python/frozen dataclass | name, description, status (active/registered/suspended), memory_count |
| memory-entity | Memory Entity | Component | Python/frozen dataclass | content, importance, source, scope, veracity, metadata |
| file-hash-vo | FileHash Value Object | Component | Python/frozen dataclass | hash_value (SHA-256, 64 hex chars) |
| file-metadata-aggregate | FileMetadataAggregate | Component | Python/frozen dataclass | Aggregate root for file metadata — chunks, relations, content composition |
| file-entity | File Entity | Component | Python/frozen dataclass | id, path, source_type, hash, file_type, size, language, status, summary, aggregated_keywords/tags |
| file-chunk-entity | FileChunk Entity | Component | Python/frozen dataclass | id, file_id, memory_id, chunk_index, start/end_line, content_hash, content_type, is_partial |
| file-relation-entity | FileRelation Entity | Component | Python/frozen dataclass | id, source/target_file_id, relation_type, strength, direction, description |
| mnemosyne-client | MnemosyneClient | Component | Python | Infrastructure adapter — wraps mnemosyne-oss with Result[T] |
| hash-index-service | HashIndexService | Component | Python | Infrastructure adapter — wraps HashIndex with Result[T] |
| file-metadata-connection | FileMetadataConnectionManager | Component | Python | Per-bank SQLite connection pool, WAL, migrations V1–V5, SQLAlchemy Engine/Session |
| mnemosyne-lib | mnemosyne-oss Library | Component_Ext | Python | External library — lazy-imported, not a remote service |
| hash-db | HashIndex SQLite DB | ComponentDbExt | SQLite | WAL-mode file hash index |
| file-db | file_metadata.db | ComponentDbExt | SQLite | Per-bank file metadata store with FTS5 |

## Notes

- All domain entities are **frozen dataclasses** (immutable) — updates produce new instances
- Result[T] is the return type for ALL domain operations; domain events live in `Result.events`, not on entities
- `MemoryBankAggregate` is the **only boundary** for memory operations; `FileMetadataAggregate` is the **only boundary** for file metadata operations
- File repositories are **concrete SQLAlchemy ORM classes** (no repository interfaces — collapsed per repo rules)
- `FileRepository.save_file` uses `session.merge()` upsert (avoids INSERT OR REPLACE cascade pitfall)
- `forgetMemory` performs file-chunk cleanup via FileService + chunk repository (only on `pure_memories` banks it is allowed)
