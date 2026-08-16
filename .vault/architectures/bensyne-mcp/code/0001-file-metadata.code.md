---
type: code
title: "Bensyne — File Metadata Domain Model"
c4_level: code
system: bensyne-mcp
createdAt: "2026-08-12T00:00:00Z"
updatedAt: "2026-08-12T16:44:16Z"
tags: [code, domain, file-metadata, aggregate]
see_also:
  - architectures/bensyne-mcp/containers/0001-container.container.md
  - architectures/bensyne-mcp/components/0001-component.component.md
  - architectures/bensyne-mcp/code/0001-code.code.md
  - concepts/0004-file-metadata-aggregate.concept.md
  - concepts/0006-file-chunk-relation.concept.md
  - specifications/0002-file-metadata-layer.spec.md
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
        FMF_CC["compose_content(mnemosyne_client, summary_only) → Result[dict]\nComposes content from chunks, emits FileContentComposedEvent"]
        FMF_TD["to_dict(relation_type, content, summary_only, client) → Result[dict]\nSerializes aggregate for MCP output"]
    end

    subgraph Entity_File["◇ File — Entity (frozen dataclass)"]
        F_I["id: str\nStable file identifier"]
        F_P["path: str\nFile path (absolute)"]
        F_ST["source_type: SourceType\nagent_session · file_system · git\ndatabase · external · remote · unknown"]
        F_H["hash: Optional[str]\nSHA-256 for deduplication"]
        F_FT["file_type: Optional[str]\nconfig · code · docs (racochu-aligned)"]
        F_SZ["size: Optional[int]"]
        F_L["language: Optional[str]"]
        F_KW["aggregated_keywords: List[str]\nAggregated from chunks"]
        F_TAGS["aggregated_tags: List[str]\nAggregated from chunks"]
        F_ST2["status: FileStatus\npending · indexed · archived · deleted"]
        F_SUM["summary: Optional[str]\nFile-level summary text"]
        F_CA["created_at: datetime"]
        F_UA["updated_at: datetime"]
    end

    subgraph Entity_FileChunk["◇ FileChunk — Entity (frozen dataclass)"]
        FC_ID["id: str\nfile_id + memory_id backfill"]
        FC_FI["file_id: str"]
        FC_MI["memory_id: str"]
        FC_CI["chunk_index: int\nPosition in sequence"]
        FC_SL["start_line: int\n0-based"]
        FC_EL["end_line: int"]
        FC_CH["content_hash: Optional[str]\nSHA-256 of chunk content"]
        FC_CT["content_type: ContentType\ntext · code · config · image · binary · unknown"]
        FC_IP["is_partial: bool\nOversized chunk truncated"]
        FC_CA["created_at: datetime"]
        FC_UA["updated_at: datetime"]
    end

    subgraph Entity_FileRelation["◇ FileRelation — Entity (frozen dataclass)"]
        FR_ID["id: str\nsource+target+type backfill"]
        FR_SF["source_file_id: str"]
        FR_TF["target_file_id: str"]
        FR_RT["relation_type: RelationType\n9 types (parent_child, sibling, backlink,\nfolder_hierarchy, cross_reference,\nversion, override, dependency, recommendation)"]
        FR_STR["strength: float\n0.0 – 1.0"]
        FR_DIR["direction: Direction\nunidirectional · bidirectional"]
        FR_DESC["description: Optional[str]"]
        FR_CA["created_at: datetime"]
        FR_UA["updated_at: datetime"]
    end

    subgraph Events_File["◇ File Domain Events"]
        EVT_FC["FileCreatedEvent\nfile_id · path"]
        EVT_FU["FileUpdatedEvent\nfile_id · changed_fields"]
        EVT_FD["FileDeletedEvent\nfile_id"]
        EVT_FIX["FileIndexCompletedEvent\nfile_id · chunk_count"]
        EVT_FCA["FileChunkAddedEvent\nfile_id · memory_id · chunk_index"]
        EVT_FCR["FileChunkRemovedEvent\nfile_id · memory_id"]
        EVT_FRC["FileRelationCreatedEvent\nsource_file_id · target_file_id · relation_type"]
        EVT_FCC["FileContentComposedEvent\nfile_id · chunks_composed"]
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
    FMF_CC -->|"composes from chunks"| Entity_FileChunk
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
- `add_chunk(chunk) -> Result[FileMetadataAggregate]` — enforces memory_id uniqueness, emits `FileChunkAddedEvent`, delegates to `File.with_chunk()`
- `remove_chunk(memory_id) -> Result[FileMetadataAggregate]` — emits `FileChunkRemovedEvent`, delegates to `File.without_chunk()`
- `add_relation(relation) -> Result[FileMetadataAggregate]` — emits `FileRelationCreatedEvent`
- `compose_content(mnemosyne_client: Callable[[str], Optional[dict]], summary_only=False) -> Result[dict]` — composes summary + chunk content, emits `FileContentComposedEvent`
- `to_dict(include_relation_type, include_content, summary_only, mnemosyne_client) -> Result[dict]` — builds MCP output dict

### File (Entity — frozen dataclass)

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Stable file identifier |
| `path` | `str` | File path (absolute) |
| `source_type` | `SourceType` | Enum: `agent_session` \| `file_system` \| `git` \| `database` \| `external` \| `remote` \| `unknown` |
| `hash` | `Optional[str]` | SHA-256 for deduplication |
| `file_type` | `Optional[str]` | config/code/docs (racochu-aligned) |
| `size` | `Optional[int]` | File size in bytes (>= 0) |
| `language` | `Optional[str]` | Programming language |
| `aggregated_keywords` | `List[str]` | Aggregated from chunks |
| `aggregated_tags` | `List[str]` | Aggregated from chunks |
| `status` | `FileStatus` | Enum: `pending` \| `indexed` \| `archived` \| `deleted` |
| `summary` | `Optional[str]` | File-level summary text |
| `created_at` | `datetime` | Creation timestamp |
| `updated_at` | `datetime` | Last update timestamp |

**Factory:** `File.of(properties) -> Result[File]` via `FileSchema`
**Operations:** `mark_indexed()`, `mark_archived()`, `mark_deleted()`, `update_metadata()`, `add_keywords()`, `add_tags()`, `with_chunk()`, `without_chunk()` — all return new frozen instances

### FileChunk (Entity — frozen dataclass)

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique id (backfilled `file_id:memory_id`) |
| `file_id` | `str` | Reference to File |
| `memory_id` | `str` | Reference to Memory (in mnemosyne) |
| `chunk_index` | `int` | Position in chunk sequence (0-based) |
| `start_line` | `int` | Starting line in source file (>= 0) |
| `end_line` | `int` | Ending line in source file (>= start_line) |
| `content_hash` | `Optional[str]` | SHA-256 of chunk content |
| `content_type` | `ContentType` | Enum: `text` \| `code` \| `config` \| `image` \| `binary` \| `unknown` |
| `is_partial` | `bool` | True if oversized chunk was truncated |
| `created_at` | `datetime` | Creation timestamp |
| `updated_at` | `datetime` | Last update timestamp |

**Factory:** `FileChunk.of(properties) -> Result[FileChunk]` via `FileChunkSchema`
**Operations:** `update_metadata(content_type, content_hash, is_partial, start_line, end_line)`

### FileRelation (Entity — frozen dataclass)

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique id (backfilled `source:target:type`) |
| `source_file_id` | `str` | Source file reference |
| `target_file_id` | `str` | Target file reference (must differ from source) |
| `relation_type` | `RelationType` | 9 types: parent_child, sibling, backlink, folder_hierarchy, cross_reference, version, override, dependency, recommendation |
| `strength` | `float` | Confidence (0.0–1.0), default 1.0 |
| `direction` | `Direction` | unidirectional \| bidirectional |
| `description` | `Optional[str]` | Human-readable explanation |
| `created_at` | `datetime` | Creation timestamp |
| `updated_at` | `datetime` | Last update timestamp |

**Factory:** `FileRelation.of(properties) -> Result[FileRelation]` via `FileRelationSchema`
**Operations:** `update_strength(strength)`, `update_description(description)`

## Repository & Storage Notes

- **Storage:** per-bank `file_metadata.db` via `FileMetadataConnectionManager` — SQLAlchemy Engine/Session, WAL mode, connection pool (default 5)
- **Migrations:** custom runner (`file_metadata_migrations.py`), versions V1–V5:
  - V1 — initial: files, file_chunks, file_relations + indexes
  - V2 — files: file_type, size, language, status + FTS5 (trigram) virtual table `files_fts` + sync triggers
  - V3 — file_chunks: id, content_hash, content_type, is_partial, updated_at + unique index + backfill
  - V4 — file_relations: id, strength, direction, description, updated_at + unique index + backfill
  - V5 — files: summary column
- **Repositories:** concrete SQLAlchemy ORM classes (no interfaces):
  - `FileRepository` — save (session.merge upsert), get_by_id, get_by_path, list, FTS5 search, delete
  - `FileChunkRepository` — save, get_chunks_by_file_id, get_chunk_by_memory_id, delete_chunk
  - `FileRelationRepository` — save, get_relations_by_file_id
- **ORM models:** `FileORM` (cascade chunks + relations), `FileChunkORM` (PK file_id+memory_id), `FileRelationORM` (PK source+target+type)

## Notes

- All file domain entities are **frozen dataclasses** — immutable; updates produce new instances
- `FileMetadataAggregate` is the **only boundary** for file metadata operations — chunk uniqueness enforced here
- Content composition is **aggregate-owned** (`compose_content()` / `to_dict()`) — use cases delegate, not build dicts
- Content is **NOT stored** in FileChunk — it exists in mnemosyne (the Memory); FileChunk stores only metadata + content_hash
- `section_header` exists as a DB column (V1) but is NOT on the FileChunk entity
- FileService: create_file, update_file, delete_file, link_chunk, create_relation, get_file, upsert_file, find_files_by_memory, remove_chunk, get_chunks_count_by_file_id
- File lifecycle: `pending → indexed → archived`; `deleted` is terminal
