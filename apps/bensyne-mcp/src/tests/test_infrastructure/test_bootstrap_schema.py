"""Fresh-database bootstrap tests (D28, spec §6.5).

A brand-new (empty) database must bootstrap cleanly to the final schema via a
single bootstrap migration (version 1) — the union of the historical V1–V6
migrations. Per D28 there is no in-place upgrade path: pre-existing dev DB
files are deleted manually by a human.

The ``source_type`` CHECK constraint is frozen with D29's canonical value set
(spec §6.5 item 2 — the one deliberate deviation from byte-identical DDL):
``obsidian | agent-sessions | vault | unknown``.

These tests pin:
- exactly one migration exists (version 1); a fresh DB applies it and lands at
  ``schema_version`` 1;
- the final schema, asserted per table: tables, columns, indexes, triggers,
  primary keys, foreign keys, and the FTS5 virtual table DDL;
- the ``source_type`` CHECK value set (accepts each D29 value, rejects the
  legacy 7-value set members and arbitrary garbage);
- bootstrap idempotency: a second bootstrap on the same DB succeeds and leaves
  the schema byte-identical.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Generator

import pytest

from src.infrastructure.storage.sqlite.file_metadata_connection import (
    FileMetadataConnectionManager,
)
from src.infrastructure.storage.sqlite.file_metadata_migrations import MIGRATIONS

# D29 canonical source_type value set (spec §6.6) — frozen into the bootstrap
# DDL by D28 (spec §6.5 item 2).
D29_SOURCE_TYPES = ["obsidian", "agent-sessions", "vault", "unknown"]

# The pre-D29 location-based 7-value set. None of these (except `unknown`)
# may be accepted by the bootstrap CHECK constraint.
LEGACY_SOURCE_TYPES = ["agent_session", "file_system", "git", "database", "external", "remote", "unknown"]

# ---------------------------------------------------------------------------
# Expected final schema — the union of historical V1–V6 (spec §6.5).
# ---------------------------------------------------------------------------

EXPECTED_TABLES = {"files", "file_chunks", "file_relations", "files_fts", "schema_version"}

EXPECTED_FILES_COLUMNS = {
    # V1
    "id",
    "path",
    "source_type",
    "file_role",
    "total_chunks",
    "file_hash",
    "created_at",
    "updated_at",
    "metadata",
    "keywords",
    "average_importance",
    "tags",
    # V2
    "file_type",
    "size",
    "language",
    "status",
    # V5
    "summary",
}

EXPECTED_FILE_CHUNKS_COLUMNS = {
    # V1
    "file_id",
    "memory_id",
    "chunk_index",
    "start_line",
    "end_line",
    "section_header",
    "created_at",
    # V3
    "id",
    "content_hash",
    "content_type",
    "is_partial",
    "updated_at",
    # V6
    "parent_unit_ref",
    "parent_unit_summary",
}

EXPECTED_FILE_RELATIONS_COLUMNS = {
    # V1
    "source_file_id",
    "target_file_id",
    "relation_type",
    "created_at",
    # V4
    "id",
    "strength",
    "direction",
    "description",
    "updated_at",
}

EXPECTED_FILES_INDEXES = {
    "idx_files_path",
    "idx_files_source_type",
    "idx_files_hash",
    "idx_files_created_at",
}

EXPECTED_FILE_CHUNKS_INDEXES = {
    "idx_file_chunks_memory_id",
    "idx_file_chunks_file_id_chunk_index",
    "idx_file_chunks_id",
}

EXPECTED_FILE_RELATIONS_INDEXES = {
    "idx_file_relations_target",
    "idx_file_relations_type",
    "idx_file_relations_target_type",
    "idx_file_relations_id",
}

EXPECTED_FTS_TRIGGERS = {"files_fts_insert", "files_fts_delete", "files_fts_update"}


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_bank_dir(tmp_path: Path) -> Path:
    """Return a temporary directory simulating a memory bank's data dir."""
    return tmp_path / "test_bank"


@pytest.fixture
def manager(tmp_bank_dir: Path) -> Generator[FileMetadataConnectionManager, None, None]:
    """Create a FileMetadataConnectionManager backed by a fresh database."""
    mgr = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
    yield mgr
    mgr.close()


def _connect(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(str(db_path))


def _schema_objects(db_path: Path) -> list[tuple[str, str, str, str]]:
    """Dump every sqlite_master object as (type, name, tbl_name, sql)."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT type, name, tbl_name, COALESCE(sql, '') FROM sqlite_master ORDER BY type, name"
        ).fetchall()
        return [tuple(row) for row in rows]
    finally:
        conn.close()


def _table_columns(db_path: Path, table: str) -> set[str]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {row[1] for row in rows}
    finally:
        conn.close()


def _table_indexes(db_path: Path, table: str) -> set[str]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name = ? AND name NOT LIKE 'sqlite%'",
            (table,),
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        conn.close()


def _table_pk_columns(db_path: Path, table: str) -> set[str]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {row[1] for row in rows if row[5] > 0}
    finally:
        conn.close()


def _table_foreign_keys(db_path: Path, table: str) -> list[tuple[str, str, str]]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
        # rows: (id, seq, table, from, to, on_update, on_delete, match)
        return sorted((row[3], row[2], row[6]) for row in rows)
    finally:
        conn.close()


def _insert_file(db_path: Path, file_id: str, source_type: str) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO files (id, path, source_type) VALUES (?, ?, ?)",
            (file_id, f"/tmp/{file_id}.md", source_type),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Single bootstrap migration (D28.2)
# ---------------------------------------------------------------------------


class TestBootstrapMigration:
    """The migration list is a single version-1 bootstrap (D28)."""

    def test_exactly_one_migration_exists(self) -> None:
        assert len(MIGRATIONS) == 1

    def test_bootstrap_migration_is_version_1(self) -> None:
        assert MIGRATIONS[0].version == 1

    def test_fresh_db_lands_at_schema_version_1(self, manager: FileMetadataConnectionManager) -> None:
        conn = _connect(manager.db_path)
        try:
            rows = conn.execute("SELECT version FROM schema_version ORDER BY version").fetchall()
            assert [row[0] for row in rows] == [1]
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Final schema — per-table snapshot (drift protection for the V1–V6 collapse)
# ---------------------------------------------------------------------------


class TestFinalSchemaSnapshot:
    """Fresh bootstrap produces the complete final schema, asserted by name."""

    def test_all_required_tables_exist(self, manager: FileMetadataConnectionManager) -> None:
        conn = _connect(manager.db_path)
        try:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            tables = {row[0] for row in rows}
            assert EXPECTED_TABLES <= tables
        finally:
            conn.close()

    def test_files_table_columns(self, manager: FileMetadataConnectionManager) -> None:
        assert _table_columns(manager.db_path, "files") == EXPECTED_FILES_COLUMNS

    def test_file_chunks_table_columns(self, manager: FileMetadataConnectionManager) -> None:
        assert _table_columns(manager.db_path, "file_chunks") == EXPECTED_FILE_CHUNKS_COLUMNS

    def test_file_relations_table_columns(self, manager: FileMetadataConnectionManager) -> None:
        assert _table_columns(manager.db_path, "file_relations") == EXPECTED_FILE_RELATIONS_COLUMNS

    def test_schema_version_table_columns(self, manager: FileMetadataConnectionManager) -> None:
        assert _table_columns(manager.db_path, "schema_version") == {"version"}

    def test_files_table_indexes(self, manager: FileMetadataConnectionManager) -> None:
        assert _table_indexes(manager.db_path, "files") == EXPECTED_FILES_INDEXES

    def test_file_chunks_table_indexes(self, manager: FileMetadataConnectionManager) -> None:
        assert _table_indexes(manager.db_path, "file_chunks") == EXPECTED_FILE_CHUNKS_INDEXES

    def test_file_relations_table_indexes(self, manager: FileMetadataConnectionManager) -> None:
        assert _table_indexes(manager.db_path, "file_relations") == EXPECTED_FILE_RELATIONS_INDEXES

    def test_files_primary_key(self, manager: FileMetadataConnectionManager) -> None:
        assert _table_pk_columns(manager.db_path, "files") == {"id"}

    def test_file_chunks_composite_primary_key(self, manager: FileMetadataConnectionManager) -> None:
        assert _table_pk_columns(manager.db_path, "file_chunks") == {"file_id", "memory_id"}

    def test_file_relations_composite_primary_key(self, manager: FileMetadataConnectionManager) -> None:
        assert _table_pk_columns(manager.db_path, "file_relations") == {
            "source_file_id",
            "target_file_id",
            "relation_type",
        }

    def test_file_chunks_foreign_key_cascades_to_files(self, manager: FileMetadataConnectionManager) -> None:
        fks = _table_foreign_keys(manager.db_path, "file_chunks")
        assert fks == [("file_id", "files", "CASCADE")]

    def test_file_relations_foreign_keys_cascade_to_files(self, manager: FileMetadataConnectionManager) -> None:
        fks = _table_foreign_keys(manager.db_path, "file_relations")
        assert fks == [("source_file_id", "files", "CASCADE"), ("target_file_id", "files", "CASCADE")]

    def test_fts5_triggers_present(self, manager: FileMetadataConnectionManager) -> None:
        conn = _connect(manager.db_path)
        try:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()
            triggers = {row[0] for row in rows}
            assert EXPECTED_FTS_TRIGGERS <= triggers
        finally:
            conn.close()

    def test_fts5_virtual_table_ddl(self, manager: FileMetadataConnectionManager) -> None:
        """The FTS5 DDL is carried over verbatim from historical V2 (spec §6.5)."""
        conn = _connect(manager.db_path)
        try:
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='files_fts'"
            ).fetchone()
            assert row is not None, "files_fts virtual table missing"
            ddl = row[0]
            assert "USING fts5" in ddl
            assert "tokenize=trigram" in ddl
            assert "content='files'" in ddl
            assert "content_rowid='rowid'" in ddl
            for column in ("path", "keywords", "tags"):
                assert column in ddl
        finally:
            conn.close()

    def test_foreign_keys_enforced_functionally(self, manager: FileMetadataConnectionManager) -> None:
        """Deleting a file cascades to its chunks and relations at the DB level."""
        conn = _connect(manager.db_path)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                "INSERT INTO files (id, path, source_type) VALUES (?, ?, ?)",
                ("fk1", "/tmp/fk1.md", "unknown"),
            )
            conn.execute(
                "INSERT INTO files (id, path, source_type) VALUES (?, ?, ?)",
                ("fk2", "/tmp/fk2.md", "unknown"),
            )
            conn.execute(
                "INSERT INTO file_chunks (file_id, memory_id, chunk_index) VALUES (?, ?, ?)",
                ("fk1", "mem_fk", 0),
            )
            conn.execute(
                "INSERT INTO file_relations (source_file_id, target_file_id, relation_type) VALUES (?, ?, ?)",
                ("fk1", "fk2", "PARENT_CHILD"),
            )
            conn.commit()
            conn.execute("DELETE FROM files WHERE id = ?", ("fk1",))
            conn.commit()
            chunks = conn.execute(
                "SELECT COUNT(*) FROM file_chunks WHERE file_id = ?", ("fk1",)
            ).fetchone()[0]
            relations = conn.execute(
                "SELECT COUNT(*) FROM file_relations WHERE source_file_id = ? OR target_file_id = ?",
                ("fk1", "fk1"),
            ).fetchone()[0]
            assert chunks == 0
            assert relations == 0
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# source_type CHECK constraint — frozen at the D29 canonical set (spec §6.5/§6.6)
# ---------------------------------------------------------------------------


class TestSourceTypeCheckConstraint:
    """The CHECK constraint accepts exactly D29's canonical value set."""

    @pytest.mark.parametrize("value", D29_SOURCE_TYPES)
    def test_accepts_each_d29_value(self, manager: FileMetadataConnectionManager, value: str) -> None:
        _insert_file(manager.db_path, f"f_{value}", value)
        conn = _connect(manager.db_path)
        try:
            row = conn.execute("SELECT source_type FROM files WHERE id = ?", (f"f_{value}",)).fetchone()
            assert row is not None
            assert row[0] == value
        finally:
            conn.close()

    @pytest.mark.parametrize("value", [v for v in LEGACY_SOURCE_TYPES if v != "unknown"])
    def test_rejects_each_legacy_value(self, manager: FileMetadataConnectionManager, value: str) -> None:
        conn = _connect(manager.db_path)
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO files (id, path, source_type) VALUES (?, ?, ?)",
                    (f"bad_{value}", f"/tmp/bad_{value}.md", value),
                )
        finally:
            conn.close()

    def test_rejects_arbitrary_invalid_value(self, manager: FileMetadataConnectionManager) -> None:
        conn = _connect(manager.db_path)
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO files (id, path, source_type) VALUES (?, ?, ?)",
                    ("bad_x", "/tmp/bad_x.md", "not_a_source_type"),
                )
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Bootstrap idempotency — second run on the same DB is a no-op (D28)
# ---------------------------------------------------------------------------


class TestBootstrapIdempotency:
    """Re-running the bootstrap on an already-bootstrapped DB succeeds and
    leaves the schema unchanged (applied migrations are no-ops)."""

    def test_second_manager_on_same_db_succeeds(self, tmp_bank_dir: Path) -> None:
        first = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        first.close()
        second = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        try:
            conn = _connect(second.db_path)
            try:
                rows = conn.execute("SELECT version FROM schema_version ORDER BY version").fetchall()
                assert [row[0] for row in rows] == [1]
            finally:
                conn.close()
        finally:
            second.close()

    def test_second_bootstrap_leaves_schema_byte_identical(self, tmp_bank_dir: Path) -> None:
        first = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        first.close()
        before = _schema_objects(tmp_bank_dir / "file_metadata.db")

        second = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        try:
            after = _schema_objects(second.db_path)
            assert after == before
        finally:
            second.close()

    def test_create_tables_is_idempotent(self, manager: FileMetadataConnectionManager) -> None:
        before = _schema_objects(manager.db_path)
        manager.create_tables()
        manager.create_tables()
        after = _schema_objects(manager.db_path)
        assert after == before
        conn = _connect(manager.db_path)
        try:
            rows = conn.execute("SELECT version FROM schema_version ORDER BY version").fetchall()
            assert [row[0] for row in rows] == [1]
        finally:
            conn.close()

    def test_bootstrap_remains_usable_after_second_run(self, tmp_bank_dir: Path) -> None:
        """Rows inserted between the two bootstraps survive the second run."""
        first = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        _insert_file(first.db_path, "survivor", "unknown")
        first.close()

        second = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        try:
            conn = _connect(second.db_path)
            try:
                row = conn.execute("SELECT source_type FROM files WHERE id = ?", ("survivor",)).fetchone()
                assert row is not None
                assert row[0] == "unknown"
            finally:
                conn.close()
        finally:
            second.close()
