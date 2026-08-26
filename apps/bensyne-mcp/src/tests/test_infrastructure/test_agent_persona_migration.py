"""Post-bootstrap ``agent-persona`` migration tests (ADR-2, ADR-5).

An EXISTING, already-bootstrapped ``file_metadata.db`` (schema version 1,
frozen 4-value ``source_type`` CHECK) must be migrated at startup by the
version-2 post-bootstrap migration so that:

- a ``source_type='agent-persona'`` row can be inserted (the critical
  acceptance requirement),
- pre-existing data survives the migration,
- indexes, FK cascades, and the FTS5 index (including its sync triggers)
  remain intact after the files-table rebuild.

The "old schema" is bootstrapped the same way the historical V1–V6 end state
was produced: migration 1 (bootstrap) applied via a raw connection with
``schema_version`` 1, as the migration runner would have left it.
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

FINAL_SCHEMA_VERSION = 2


@pytest.fixture
def tmp_bank_dir(tmp_path: Path) -> Path:
    return tmp_path / "test_bank"


@pytest.fixture
def bootstrapped_db(tmp_bank_dir: Path) -> Path:
    """Create an already-bootstrapped (version 1, pre-agent-persona) DB.

    Seeds one file row with chunks, a relation, and FTS-searchable content so
    data preservation and index integrity can be asserted after migration.
    """
    db_path = tmp_bank_dir / "file_metadata.db"
    tmp_bank_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(MIGRATIONS[0].up_sql)
        conn.execute("INSERT INTO schema_version (version) VALUES (1)")
        conn.execute(
            "INSERT INTO files (id, path, source_type, keywords, tags) VALUES (?, ?, ?, ?, ?)",
            ("pre_existing", "/tmp/pre_existing.md", "vault", "sqlite keyword", "migration"),
        )
        conn.execute(
            "INSERT INTO file_chunks (file_id, memory_id, chunk_index) VALUES (?, ?, ?)",
            ("pre_existing", "mem_pre", 0),
        )
        conn.execute(
            "INSERT INTO files (id, path, source_type) VALUES (?, ?, ?)",
            ("pre_existing_target", "/tmp/pre_existing_target.md", "unknown"),
        )
        conn.execute(
            "INSERT INTO file_relations (source_file_id, target_file_id, relation_type) VALUES (?, ?, ?)",
            ("pre_existing", "pre_existing_target", "PARENT_CHILD"),
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _connect(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(str(db_path))


def _schema_version(db_path: Path) -> int:
    conn = _connect(db_path)
    try:
        return conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()[0]
    finally:
        conn.close()


class TestExistingDbMigratedAtStartup:
    """An existing bootstrapped DB is migrated when the manager starts up."""

    def test_existing_db_reaches_final_schema_version(self, bootstrapped_db: Path, tmp_bank_dir: Path) -> None:
        mgr = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        try:
            mgr.create_tables()  # startup path — applies pending migrations
            assert _schema_version(tmp_bank_dir / "file_metadata.db") == FINAL_SCHEMA_VERSION
        finally:
            mgr.close()

    def test_agent_persona_insert_succeeds_after_startup_migration(
        self, bootstrapped_db: Path, tmp_bank_dir: Path
    ) -> None:
        """Critical acceptance requirement: after startup migration, an
        agent-persona row inserts on the previously bootstrapped DB."""
        mgr = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        mgr.create_tables()
        try:
            conn = mgr.get_connection()
            try:
                conn.execute(
                    "INSERT INTO files (id, path, source_type) VALUES (?, ?, ?)",
                    ("persona_node_1", "/tmp/persona_node_1.md", "agent-persona"),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT source_type FROM files WHERE id = ?", ("persona_node_1",)
                ).fetchone()
                assert row is not None
                assert row[0] == "agent-persona"
            finally:
                mgr.close_connection(conn)
        finally:
            mgr.close()

    def test_invalid_source_type_still_rejected_after_migration(
        self, bootstrapped_db: Path, tmp_bank_dir: Path
    ) -> None:
        """The migrated CHECK is still closed: garbage values fail."""
        mgr = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        mgr.create_tables()
        try:
            conn = mgr.get_connection()
            try:
                with pytest.raises(sqlite3.IntegrityError):
                    conn.execute(
                        "INSERT INTO files (id, path, source_type) VALUES (?, ?, ?)",
                        ("bad_x", "/tmp/bad_x.md", "not_a_source_type"),
                    )
                with pytest.raises(sqlite3.IntegrityError):
                    conn.execute(
                        "INSERT INTO files (id, path, source_type) VALUES (?, ?, ?)",
                        ("bad_legacy", "/tmp/bad_legacy.md", "file_system"),
                    )
            finally:
                mgr.close_connection(conn)
        finally:
            mgr.close()


class TestMigrationPreservesDataAndIntegrity:
    """The files-table rebuild keeps data, FKs, indexes, and FTS working."""

    def test_pre_existing_rows_survive_migration(self, bootstrapped_db: Path, tmp_bank_dir: Path) -> None:
        mgr = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        mgr.create_tables()
        try:
            conn = _connect(tmp_bank_dir / "file_metadata.db")
            try:
                row = conn.execute(
                    "SELECT path, source_type, keywords, tags FROM files WHERE id = ?",
                    ("pre_existing",),
                ).fetchone()
                assert row is not None
                assert row[0] == "/tmp/pre_existing.md"
                assert row[1] == "vault"
                assert row[2] == "sqlite keyword"
                assert row[3] == "migration"
                chunks = conn.execute("SELECT COUNT(*) FROM file_chunks").fetchone()[0]
                assert chunks == 1
                relations = conn.execute("SELECT COUNT(*) FROM file_relations").fetchone()[0]
                assert relations == 1
            finally:
                conn.close()
        finally:
            mgr.close()

    def test_files_indexes_survive_migration(self, bootstrapped_db: Path, tmp_bank_dir: Path) -> None:
        mgr = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        mgr.create_tables()
        try:
            conn = _connect(tmp_bank_dir / "file_metadata.db")
            try:
                rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' "
                    "AND tbl_name='files' AND name NOT LIKE 'sqlite%'"
                ).fetchall()
                indexes = {row[0] for row in rows}
                assert indexes == {
                    "idx_files_path",
                    "idx_files_source_type",
                    "idx_files_hash",
                    "idx_files_created_at",
                }
            finally:
                conn.close()
        finally:
            mgr.close()

    def test_foreign_key_cascade_still_works_after_migration(
        self, bootstrapped_db: Path, tmp_bank_dir: Path
    ) -> None:
        mgr = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        mgr.create_tables()
        try:
            conn = _connect(tmp_bank_dir / "file_metadata.db")
            try:
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("DELETE FROM files WHERE id = ?", ("pre_existing",))
                conn.commit()
                chunks = conn.execute(
                    "SELECT COUNT(*) FROM file_chunks WHERE file_id = ?", ("pre_existing",)
                ).fetchone()[0]
                relations = conn.execute(
                    "SELECT COUNT(*) FROM file_relations WHERE source_file_id = ?",
                    ("pre_existing",),
                ).fetchone()[0]
                assert chunks == 0
                assert relations == 0
            finally:
                conn.close()
        finally:
            mgr.close()

    def test_fts_still_searchable_after_migration(self, bootstrapped_db: Path, tmp_bank_dir: Path) -> None:
        mgr = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        mgr.create_tables()
        try:
            conn = _connect(tmp_bank_dir / "file_metadata.db")
            try:
                rows = conn.execute(
                    "SELECT f.id FROM files_fts "
                    "JOIN files f ON f.rowid = files_fts.rowid "
                    "WHERE files_fts MATCH ?"
                , ("sqlite",)).fetchall()
                assert [row[0] for row in rows] == ["pre_existing"]
            finally:
                conn.close()
        finally:
            mgr.close()

    def test_fts_triggers_still_maintain_index_after_migration(
        self, bootstrapped_db: Path, tmp_bank_dir: Path
    ) -> None:
        """Post-migration inserts must be found by FTS (triggers recreated)."""
        mgr = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        mgr.create_tables()
        try:
            conn = mgr.get_connection()
            try:
                conn.execute(
                    "INSERT INTO files (id, path, source_type, keywords) VALUES (?, ?, ?, ?)",
                    ("post_migration", "/tmp/post_migration.md", "agent-persona", "fresh keyword"),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT f.id FROM files_fts "
                    "JOIN files f ON f.rowid = files_fts.rowid "
                    "WHERE files_fts MATCH ?",
                    ("fresh",),
                ).fetchone()
                assert row is not None
                assert row[0] == "post_migration"
            finally:
                mgr.close_connection(conn)
        finally:
            mgr.close()


class TestFreshDbAndIdempotentStartup:
    """Fresh DBs apply bootstrap + post-bootstrap; restarts are no-ops."""

    def test_fresh_db_accepts_agent_persona(self, tmp_bank_dir: Path) -> None:
        mgr = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        mgr.create_tables()
        try:
            conn = mgr.get_connection()
            try:
                conn.execute(
                    "INSERT INTO files (id, path, source_type) VALUES (?, ?, ?)",
                    ("persona_fresh", "/tmp/persona_fresh.md", "agent-persona"),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT source_type FROM files WHERE id = ?", ("persona_fresh",)
                ).fetchone()
                assert row is not None
                assert row[0] == "agent-persona"
            finally:
                mgr.close_connection(conn)
        finally:
            mgr.close()

    def test_restart_on_migrated_db_is_a_no_op(
        self, bootstrapped_db: Path, tmp_bank_dir: Path
    ) -> None:
        """Second startup on an already-migrated DB: no errors, same schema,
        data intact."""
        first = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        first.create_tables()
        first.close()

        second = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        try:
            second.create_tables()
            assert _schema_version(tmp_bank_dir / "file_metadata.db") == FINAL_SCHEMA_VERSION
            conn = _connect(tmp_bank_dir / "file_metadata.db")
            try:
                row = conn.execute(
                    "SELECT source_type FROM files WHERE id = ?", ("pre_existing",)
                ).fetchone()
                assert row is not None
                assert row[0] == "vault"
            finally:
                conn.close()
        finally:
            second.close()
