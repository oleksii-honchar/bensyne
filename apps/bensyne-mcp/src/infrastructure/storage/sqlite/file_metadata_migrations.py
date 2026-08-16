"""Migration definitions for file metadata SQLite schema.

Each migration is a Migration dataclass with version, up_sql, and description.
Migrations are applied sequentially from version 1 to the latest.
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
# Migration V1 — Initial schema: files, file_chunks, file_relations
# ---------------------------------------------------------------------------

_MIGRATION_V1_UP_SQL = """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

-- files table
CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('agent_session', 'file_system', 'git', 'database', 'external', 'remote', 'unknown')),
    file_role TEXT CHECK (file_role IN ('config', 'code', 'docs') OR file_role IS NULL),
    total_chunks INTEGER NOT NULL DEFAULT 0,
    file_hash TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    metadata TEXT,
    keywords TEXT,
    average_importance REAL NOT NULL DEFAULT 0.5,
    tags TEXT
);

-- Indexes for files
CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);
CREATE INDEX IF NOT EXISTS idx_files_source_type ON files(source_type);
CREATE INDEX IF NOT EXISTS idx_files_hash ON files(file_hash);
CREATE INDEX IF NOT EXISTS idx_files_created_at ON files(created_at);

-- file_chunks table (junction between files and memories)
CREATE TABLE IF NOT EXISTS file_chunks (
    file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    memory_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    start_line INTEGER,
    end_line INTEGER,
    section_header TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (file_id, memory_id)
);

-- Indexes for file_chunks
CREATE INDEX IF NOT EXISTS idx_file_chunks_memory_id ON file_chunks(memory_id);
CREATE INDEX IF NOT EXISTS idx_file_chunks_file_id_chunk_index ON file_chunks(file_id, chunk_index);

-- file_relations table
CREATE TABLE IF NOT EXISTS file_relations (
    source_file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    target_file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_file_id, target_file_id, relation_type)
);

-- Indexes for file_relations
CREATE INDEX IF NOT EXISTS idx_file_relations_target ON file_relations(target_file_id);
CREATE INDEX IF NOT EXISTS idx_file_relations_type ON file_relations(relation_type);
CREATE INDEX IF NOT EXISTS idx_file_relations_target_type ON file_relations(target_file_id, relation_type);
"""

# ---------------------------------------------------------------------------
# Migration V2 — Add missing columns and FTS5 for full-text search
# ---------------------------------------------------------------------------

_MIGRATION_V2_UP_SQL = """
-- Add missing columns to files table for File entity mapping
ALTER TABLE files ADD COLUMN file_type TEXT;
ALTER TABLE files ADD COLUMN size INTEGER;
ALTER TABLE files ADD COLUMN language TEXT;
ALTER TABLE files ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'indexed', 'archived', 'deleted'));

-- FTS5 virtual table for full-text search on path, keywords, and tags
-- Uses trigram tokenizer for case-insensitive substring matching
CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
    path,
    keywords,
    tags,
    tokenize=trigram,
    content='files',
    content_rowid='rowid'
);

-- Triggers to keep FTS index in sync
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
"""

# ---------------------------------------------------------------------------
# Migration V3 — Add missing columns to file_chunks for FileChunk entity mapping
# ---------------------------------------------------------------------------

_MIGRATION_V3_UP_SQL = """
-- Add missing columns to file_chunks table for FileChunk entity mapping
ALTER TABLE file_chunks ADD COLUMN id TEXT;
ALTER TABLE file_chunks ADD COLUMN content_hash TEXT;
ALTER TABLE file_chunks ADD COLUMN content_type TEXT;
ALTER TABLE file_chunks ADD COLUMN is_partial INTEGER NOT NULL DEFAULT 0;
ALTER TABLE file_chunks ADD COLUMN updated_at TIMESTAMP;

-- Unique index on id for efficient lookups
CREATE UNIQUE INDEX IF NOT EXISTS idx_file_chunks_id ON file_chunks(id);

-- Backfill id from file_id + memory_id for existing rows
UPDATE file_chunks SET id = file_id || ':' || memory_id WHERE id IS NULL;
"""

# ---------------------------------------------------------------------------
# Migration V4 — Add missing columns to file_relations for FileRelation entity mapping
# ---------------------------------------------------------------------------

_MIGRATION_V4_UP_SQL = """
-- Add missing columns to file_relations table for FileRelation entity mapping
ALTER TABLE file_relations ADD COLUMN id TEXT;
ALTER TABLE file_relations ADD COLUMN strength REAL NOT NULL DEFAULT 1.0;
ALTER TABLE file_relations ADD COLUMN direction TEXT NOT NULL DEFAULT 'unidirectional';
ALTER TABLE file_relations ADD COLUMN description TEXT;
ALTER TABLE file_relations ADD COLUMN updated_at TIMESTAMP;

-- Unique index on id for efficient lookups
CREATE UNIQUE INDEX IF NOT EXISTS idx_file_relations_id ON file_relations(id);

-- Backfill id from source_file_id + target_file_id + relation_type for existing rows
UPDATE file_relations SET id = source_file_id || ':' || target_file_id || ':' || relation_type WHERE id IS NULL;
"""

# ---------------------------------------------------------------------------
# Migration V5 — Add summary column to files table
# ---------------------------------------------------------------------------

_MIGRATION_V5_UP_SQL = """
-- Add summary column to files table for file-level summary text
ALTER TABLE files ADD COLUMN summary TEXT;
"""

MIGRATIONS: list[Migration] = [
    Migration(
        version=1,
        up_sql=_MIGRATION_V1_UP_SQL,
        description="Initial schema: files, file_chunks, file_relations with indexes",
    ),
    Migration(
        version=2,
        up_sql=_MIGRATION_V2_UP_SQL,
        description="Add file_type, size, language, status columns and FTS5 full-text search",
    ),
    Migration(
        version=3,
        up_sql=_MIGRATION_V3_UP_SQL,
        description="Add id, content_hash, content_type, is_partial, updated_at to file_chunks",
    ),
    Migration(
        version=4,
        up_sql=_MIGRATION_V4_UP_SQL,
        description="Add id, strength, direction, description, updated_at to file_relations",
    ),
    Migration(
        version=5,
        up_sql=_MIGRATION_V5_UP_SQL,
        description="Add summary column to files table",
    ),
]
