---
type: code
title: "Bensyne — File Metadata Domain Model"
c4_level: code
system: bensyne
createdAt: "2026-08-12T00:00:00Z"
updatedAt: "2026-08-12T00:00:00Z"
tags: [code, domain, file-metadata, aggregate]
see_also:
  - "architectures/bensyne/0001-container.architecture.md"
  - "architectures/bensyne/0001-component.architecture.md"
  - "architectures/bensyne/0001-code.architecture.md"
  - "concepts/0004-file-metadata-aggregate.concept.md"
  - "concepts/0006-file-chunk-relation.concept.md"
  - "specifications/0002-file-metadata-layer.spec.md"
linked_elements:
  - file-metadata-aggregate
  - file
  - file-chunk
  - file-relation
  - file-events
  - file-repositories
---

# Bensyne — File Metadata Domain Model

## Diagram

```mermaid
flowchart TB
    subgraph AggregateRoot["◇ FileMetadataAggregate — Aggregate Root"]
        FMF_F["file: File"]
        FMF_C["chunks: List[FileChunk]"]
        FMF_R["relations: List[FileRelation]"]

        FMF_AC["add_chunk(chunk) → Result[FileMetadataAggregate]\nEnforces uniqueness, emits FileChunkAddedEvent"]
        FMF_RC["remove_chunk(memory_id) → Result[FileMetadataAggregate]\nEmits FileChunkRemovedEvent"]
        FMF_AR["add_relation(relation) → Result[FileMetadataAggregate]\nEmits FileRelationCreatedEvent"]
        FMF_CC["compose_content(client, summary_only) → Result[dict]\nComposes content from chunks, emits FileContentComposedEvent"]
        FMF_TD["to_dict() → dict\nSerializes aggregate for MCP output"]
    end

    subgraph Entity_File["◇ File — Entity (frozen dataclass)"]
        F_I["id: str\nStable file identifier (UUID)"]
        F_P["path: str\nFile path (absolute)"]
        F_ST["source_type: SourceType\nagent-session · obsidian · per-repo-vault"]
        F_FR["file_role: Optional[FileRole]\nconfig · code · docs"]
        F_TC["total_chunks: int"]
        F_FH["file_hash: Optional[str]\nSHA-256 for deduplication"]
        F_CA["created_at: datetime"]
        F_UA["updated_at: Optional[datetime]"]
        F_MD["metadata: Optional[dict]\nSource-type-specific metadata"]
        F_KW["keywords: List[str]\nAggregated from chunks"]
        F_AI["average_importance: float\nMean across all chunks"]
        F_TAGS["tags: List[str]\nAggregated from chunks"]
    end

    subgraph Entity_FileChunk["◇ FileChunk — Entity (frozen dataclass)"]
        FC_FI["file_id: str"]
        FC_MI["memory_id: str"]
        FC_CI["chunk_index: int\nPosition in sequence"]
        FC_SL["start_line: Optional[int]"]
        FC_EL["end_line: Optional[int]"]
        FC_SH["section_header: str"]
        FC_CA["created_at: datetime"]
    end

    subgraph Entity_FileRelation["◇ FileRelation — Entity (frozen dataclass)"]
        FR_SF["source_file_id: str"]
        FR_TF["target_file_id: str"]
        FR_RT["relation_type: RelationType\n9 types (PARENT_CHILD, SIBLING, etc.)"]
        FR_STR["strength: float\n0.0 – 1.0"]
        FR_DIR["direction: Direction\nUNIDIRECTIONAL · BIDIRECTIONAL"]
        FR_CA["created_at: datetime"]
    end

    subgraph Events_File["◇ File Domain Events"]
        EVT_FC["FileCreatedEvent\nfile_id · path · source_type"]
        EVT_FCA["FileChunkAddedEvent\nfile_id · memory_id · chunk_index"]
        EVT_FCR["FileChunkRemovedEvent\nfile_id · memory_id"]
        EVT_FRC["FileRelationCreatedEvent\nsource_file_id · target_file_id · relation_type"]
        EVT_FCC["FileContentComposedEvent\nfile_id · status · chunk_count"]
    end

    FMF_F -->|"contains"| Entity_File
    FMF_C -->|"contains (List)"| Entity_FileChunk
    FMF_R -->|"contains (List)"| Entity_FileRelation
    FMF_AC -->|"validates & adds"| Entity_FileChunk
    FMF_AC -->|"produces"| EVT_FCA
    FMF_RC -->|"validates & removes"| Entity_FileChunk
    FMF_RC -->|"produces"| EVT_FCR
    FMF_AR -->|"validates & adds"| Entity_FileRelation
    FMF_AR -->|"produces"| EVT_FRC
    FMF_CC -->|"delegates to FileMetadataAggregate.compose_content"| Entity_FileChunk
    FMF_CC -->|"produces"| EVT_FCC

    classDef aggregate fill:#fef9e7,stroke:#f1c40f,stroke-width:2px,color:#333
    classDef entity fill:#eaf2f8,stroke:#3498db,stroke-width:2px,color:#333
    classDef event fill:#fdf2e9,stroke:#e67e22,stroke-width:2px,color:#333

    class AggregateRoot aggregate
    class Entity_File,Entity_FileChunk,Entity_FileRelation entity
    class Events_File event
```

## Entity Schema Reference

### FileMetadataAggregate (Aggregate Root)

| Field | Type | Description |
|-------|------|-------------|
| `file` | `File` | Reference to the file entity |
| `chunks` | `List[FileChunk]` | Collection of chunk entities |
| `relations` | `List[FileRelation]` | Collection of relation entities |

**Operations:**
- `of(file, chunks, relations) -> Result[FileMetadataAggregate]` — factory
- `add_chunk(chunk) -> Result[FileMetadataAggregate]` — enforces uniqueness, emits `FileChunkAddedEvent`, delegates to `File.with_chunk()`
- `remove_chunk(memory_id) -> Result[FileMetadataAggregate]` — emits `FileChunkRemovedEvent`, delegates to `File.without_chunk()`
- `add_relation(relation) -> Result[FileMetadataAggregate]` — emits `FileRelationCreatedEvent`
- `compose_content(mnemosyne_client, summary_only=False) -> Result[dict]` — composes content from chunks, emits `FileContentComposedEvent`
- `to_dict() -> dict` — serializes aggregate for MCP tool output

### File (Entity — frozen dataclass)

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Stable file identifier (UUID) |
| `path` | `str` | File path (absolute) |
| `source_type` | `SourceType` | Enum: `agent-session` \| `obsidian` \| `per-repo-vault` |
| `file_role` | `Optional[FileRole]` | Enum: `config` \| `code` \| `docs` |
| `total_chunks` | `int` | Number of chunks |
| `file_hash` | `Optional[str]` | SHA-256 for deduplication |
| `created_at` | `datetime` | Creation timestamp |
| `updated_at` | `Optional[datetime]` | Last update timestamp |
| `metadata` | `Optional[dict]` | Source-type-specific metadata |
| `keywords` | `List[str]` | Aggregated from chunks |
| `average_importance` | `float` | Mean across all chunks |
| `tags` | `List[str]` | Aggregated from chunks |

**Factory:** `File.of(properties) -> Result[File]` via `FileSchema`
**Operations:** `with_chunk(importance, tags, keywords) -> Result[File]` — updates total_chunks, average_importance, merges keywords/tags; `without_chunk(importance) -> Result[File]` — decrements total_chunks, recomputes average_importance

### FileChunk (Entity — frozen dataclass)

| Field | Type | Description |
|-------|------|-------------|
| `file_id` | `str` | Reference to File |
| `memory_id` | `str` | Reference to Memory (in mnemosyne) |
| `chunk_index` | `int` | Position in chunk sequence (0-based) |
| `start_line` | `Optional[int]` | Starting line in source file |
| `end_line` | `Optional[int]` | Ending line in source file |
| `section_header` | `str` | Ancestor heading |
| `created_at` | `datetime` | Creation timestamp |

**Factory:** `FileChunk.of(properties) -> Result[FileChunk]` via `FileChunkSchema`

### FileRelation (Entity — frozen dataclass)

| Field | Type | Description |
|-------|------|-------------|
| `source_file_id` | `str` | Source file reference |
| `target_file_id` | `str` | Target file reference |
| `relation_type` | `RelationType` | 9 types: PARENT_CHILD, SIBLING, BACKLINK, FOLDER_HIERARCHY, CROSS_REFERENCE, VERSION, OVERRIDE, DEPENDENCY, RECOMMENDATION |
| `strength` | `float` | Confidence (0.0–1.0) |
| `direction` | `Direction` | UNIDIRECTIONAL or BIDIRECTIONAL |
| `created_at` | `datetime` | Creation timestamp |

**Factory:** `FileRelation.of(properties) -> Result[FileRelation]` via `FileRelationSchema`

## Notes

- All file domain entities are **frozen dataclasses** — immutable; updates produce new instances
- `FileMetadataAggregate` is the **only boundary** for file metadata operations — chunk uniqueness enforced here
- Content composition moved to aggregate (`compose_content()`) — use case delegates to aggregate, not builds dict
- Content is **NOT stored** in FileChunk — it exists in mnemosyne (the Memory)
- FileRepository, FileChunkRepository, FileRelationRepository are **collapsed to concrete types** (no interfaces needed)
- 5 domain event types: `FileCreatedEvent`, `FileChunkAddedEvent`, `FileChunkRemovedEvent`, `FileRelationCreatedEvent`, `FileContentComposedEvent`
