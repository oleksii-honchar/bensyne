"""Fresh bootstrap migration for the file metadata SQLite schema (D28).

The historical V1–V6 migrations are collapsed into a **single bootstrap
migration (version 1)** whose DDL is the union of all six — the final schema
is byte-identical to the V1–V6 end state (V2's FTS5 DDL carried over
verbatim), with one deliberate deviation: the ``source_type`` CHECK
constraint is frozen with D29's canonical value set
(``obsidian | agent-sessions | vault | unknown``, spec §6.5/§6.6).

**No in-place upgrade path exists (by design — D28).** A pre-existing dev DB
file with an old schema (any ``schema_version`` other than 1, or a legacy
layout) is never migrated by this code — it is **deleted manually** by a
human. No real data exists, so nothing is lost; the code refuses to silently
upgrade or destroy.

The runner (``FileMetadataConnectionManager``) applies unapplied migrations
in order; a fresh DB applies exactly one (the bootstrap).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Migration:
    """A single schema migration with version, SQL, and description."""

    version: int
    up_sql: str
    description: str


# ---------------------------------------------------------------------------
# Bootstrap migration (version 1) — the union of historical V1–V6
# ---------------------------------------------------------------------------

_BOOTSTRAP_UP_SQL = """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

-- files table (V1 columns + V2 file_type/size/language/status + V5 summary)
CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('obsidian', 'agent-sessions', 'vault', 'unknown')),
    file_role TEXT CHECK (file_role IN ('config', 'code', 'docs') OR file_role IS NULL),
    total_chunks INTEGER NOT NULL DEFAULT 0,
    file_hash TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    metadata TEXT,
    keywords TEXT,
    average_importance REAL NOT NULL DEFAULT 0.5,
    tags TEXT,
    file_type TEXT,
    size INTEGER,
    language TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'indexed', 'archived', 'deleted')),
    summary TEXT
);

-- Indexes for files
CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);
CREATE INDEX IF NOT EXISTS idx_files_source_type ON files(source_type);
CREATE INDEX IF NOT EXISTS idx_files_hash ON files(file_hash);
CREATE INDEX IF NOT EXISTS idx_files_created_at ON files(created_at);

-- file_chunks table (junction between files and memories)
-- V1 columns + V3 id/content_hash/content_type/is_partial/updated_at
-- + V6 parent_unit_ref/parent_unit_summary
CREATE TABLE IF NOT EXISTS file_chunks (
    file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    memory_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    start_line INTEGER,
    end_line INTEGER,
    section_header TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id TEXT,
    content_hash TEXT,
    content_type TEXT,
    is_partial INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP,
    parent_unit_ref TEXT,
    parent_unit_summary TEXT,
    PRIMARY KEY (file_id, memory_id)
);

-- Indexes for file_chunks
CREATE INDEX IF NOT EXISTS idx_file_chunks_memory_id ON file_chunks(memory_id);
CREATE INDEX IF NOT EXISTS idx_file_chunks_file_id_chunk_index ON file_chunks(file_id, chunk_index);
CREATE UNIQUE INDEX IF NOT EXISTS idx_file_chunks_id ON file_chunks(id);

-- file_relations table
-- V1 columns + V4 id/strength/direction/description/updated_at
CREATE TABLE IF NOT EXISTS file_relations (
    source_file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    target_file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id TEXT,
    strength REAL NOT NULL DEFAULT 1.0,
    direction TEXT NOT NULL DEFAULT 'unidirectional',
    description TEXT,
    updated_at TIMESTAMP,
    PRIMARY KEY (source_file_id, target_file_id, relation_type)
);

-- Indexes for file_relations
CREATE INDEX IF NOT EXISTS idx_file_relations_target ON file_relations(target_file_id);
CREATE INDEX IF NOT EXISTS idx_file_relations_type ON file_relations(relation_type);
CREATE INDEX IF NOT EXISTS idx_file_relations_target_type ON file_relations(target_file_id, relation_type);
CREATE UNIQUE INDEX IF NOT EXISTS idx_file_relations_id ON file_relations(id);

-- FTS5 virtual table for full-text search on path, keywords, and tags
-- (V2 DDL carried over verbatim — trigram tokenizer for case-insensitive
-- substring matching)
CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
    path,
    keywords,
    tags,
    tokenize=trigram,
    content='files',
    content_rowid='rowid'
);

-- Triggers to keep FTS index in sync (V2, verbatim)
CREATE TRIGGER IF NOT EXISTS files_fts_insert AFTER INSERT ON files BEGIN
    INSERT INTO files_fts(rowid, path, keywords, tags)
    VALUES (NEW.rowid, NEW.path, NEW.keywords, NEW.tags);
END;

CREATE TRIGGER IF NOT EXISTS files_fts_delete AFTER DELETE ON files BEGIN
    INSERT INTO files_fts(files_fts, rowid, path, keywords, tags)
    VALUES ('delete', OLD.rowid, OLD.path, OLD.keywords, OLD.tags);
END;

CREATE TRIGGER IF NOT EXISTS files_fts_update AFTER UPDATE ON files BEGIN
    INSERT INTO files_fts(files_fts, rowid, path, keywords, tags)
    VALUES ('delete', OLD.rowid, OLD.path, OLD.keywords, OLD.tags);
    INSERT INTO files_fts(rowid, path, keywords, tags)
    VALUES (NEW.rowid, NEW.path, NEW.keywords, NEW.tags);
END;

-- Backfills from historical V3/V4 — no-ops on a fresh database (kept for
-- DDL fidelity with the V1–V6 union).
UPDATE file_chunks SET id = file_id || ':' || memory_id WHERE id IS NULL;
UPDATE file_relations SET id = source_file_id || ':' || target_file_id || ':' || relation_type WHERE id IS NULL;
"""

MIGRATIONS: list[Migration] = [
    Migration(
        version=1,
        up_sql=_BOOTSTRAP_UP_SQL,
        description=(
            "Bootstrap: files, file_chunks, file_relations (full union of "
            "historical V1–V6) with indexes, FTS5 full-text search, and the "
            "D29 source_type CHECK set"
        ),
    ),
]
