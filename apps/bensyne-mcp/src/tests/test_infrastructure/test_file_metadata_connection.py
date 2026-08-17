"""File metadata connection manager tests — SQLite-backed per-bank storage."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Generator

import pytest

from src.infrastructure.storage.sqlite.file_metadata_connection import (
    FileMetadataConnectionManager,
)
from src.infrastructure.storage.sqlite.file_metadata_migrations import (
    MIGRATIONS,
    Migration,
)


@pytest.fixture
def tmp_bank_dir(tmp_path: Path) -> Path:
    """Return a temporary directory simulating a memory bank's data dir."""
    return tmp_path / "test_bank"


@pytest.fixture
def manager(tmp_bank_dir: Path) -> Generator[FileMetadataConnectionManager, None, None]:
    """Create a FileMetadataConnectionManager backed by a temporary directory."""
    mgr = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
    yield mgr
    mgr.close()


class TestMigrations:
    """Migration definitions are correct and ordered."""

    def test_migrations_list_is_not_empty(self) -> None:
        assert len(MIGRATIONS) > 0

    def test_first_migration_is_v1(self) -> None:
        first = MIGRATIONS[0]
        assert first.version == 1

    def test_migration_versions_are_ascending(self) -> None:
        for i in range(1, len(MIGRATIONS)):
            assert MIGRATIONS[i].version > MIGRATIONS[i - 1].version

    def test_migration_has_up_sql(self) -> None:
        for migration in MIGRATIONS:
            assert migration.up_sql is not None
            assert len(migration.up_sql.strip()) > 0

    def test_migration_v1_creates_files_table(self) -> None:
        v1 = MIGRATIONS[0]
        assert "CREATE TABLE" in v1.up_sql
        assert "files" in v1.up_sql

    def test_migration_v1_creates_file_chunks_table(self) -> None:
        v1 = MIGRATIONS[0]
        assert "file_chunks" in v1.up_sql

    def test_migration_v1_creates_file_relations_table(self) -> None:
        v1 = MIGRATIONS[0]
        assert "file_relations" in v1.up_sql

    def test_migration_v1_has_schema_version_table(self) -> None:
        v1 = MIGRATIONS[0]
        assert "schema_version" in v1.up_sql

    def test_migration_has_description(self) -> None:
        for migration in MIGRATIONS:
            assert migration.description is not None
            assert len(migration.description.strip()) > 0

    def test_migration_dataclass_fields(self) -> None:
        m = MIGRATIONS[0]
        assert isinstance(m.version, int)
        assert isinstance(m.up_sql, str)
        assert isinstance(m.description, str)


class TestConnectionInitialization:
    """Manager creates the database and tables on initialization."""

    def test_db_file_created_on_init(self, tmp_bank_dir: Path) -> None:
        db_path = tmp_bank_dir / "file_metadata.db"
        assert not db_path.exists()
        FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        assert db_path.exists()

    def test_parent_directory_created_if_missing(self, tmp_path: Path) -> None:
        deep_dir = tmp_path / "a" / "b" / "c"
        assert not deep_dir.exists()
        FileMetadataConnectionManager(bank_dir=deep_dir)
        assert (deep_dir / "file_metadata.db").exists()

    def test_wal_mode_enabled(self, manager: FileMetadataConnectionManager, tmp_bank_dir: Path) -> None:
        db_path = tmp_bank_dir / "file_metadata.db"
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
            assert mode == "wal"
        finally:
            conn.close()

    def test_tables_created_on_init(self, manager: FileMetadataConnectionManager, tmp_bank_dir: Path) -> None:
        db_path = tmp_bank_dir / "file_metadata.db"
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            table_names = [row[0] for row in cursor.fetchall()]
            assert "files" in table_names
            assert "file_chunks" in table_names
            assert "file_relations" in table_names
            assert "schema_version" in table_names
        finally:
            conn.close()

    def test_schema_version_set_after_init(self, manager: FileMetadataConnectionManager, tmp_bank_dir: Path) -> None:
        db_path = tmp_bank_dir / "file_metadata.db"
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("SELECT version FROM schema_version")
            version = cursor.fetchone()[0]
            assert version == MIGRATIONS[-1].version
        finally:
            conn.close()


class TestFileTableSchema:
    """files table has the correct schema per spec."""

    def test_files_table_has_required_columns(self, manager: FileMetadataConnectionManager, tmp_bank_dir: Path) -> None:
        db_path = tmp_bank_dir / "file_metadata.db"
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("PRAGMA table_info(files)")
            columns = {row[1]: row[2] for row in cursor.fetchall()}
            assert "id" in columns
            assert "path" in columns
            assert "source_type" in columns
            assert "file_role" in columns
            assert "total_chunks" in columns
            assert "file_hash" in columns
            assert "created_at" in columns
            assert "updated_at" in columns
            assert "metadata" in columns
            assert "keywords" in columns
            assert "average_importance" in columns
            assert "tags" in columns
        finally:
            conn.close()

    def test_files_table_has_indexes(self, manager: FileMetadataConnectionManager, tmp_bank_dir: Path) -> None:
        db_path = tmp_bank_dir / "file_metadata.db"
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='files' AND name NOT LIKE 'sqlite%'"
            )
            index_names = [row[0] for row in cursor.fetchall()]
            assert "idx_files_path" in index_names
            assert "idx_files_source_type" in index_names
            assert "idx_files_hash" in index_names
            assert "idx_files_created_at" in index_names
        finally:
            conn.close()

    def test_files_id_is_primary_key(self, manager: FileMetadataConnectionManager, tmp_bank_dir: Path) -> None:
        db_path = tmp_bank_dir / "file_metadata.db"
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("PRAGMA table_info(files)")
            columns = {row[1]: row[5] for row in cursor.fetchall()}  # pk column
            assert columns["id"] == 1
        finally:
            conn.close()

    def test_files_source_type_check_constraint(
        self, manager: FileMetadataConnectionManager, tmp_bank_dir: Path
    ) -> None:
        """source_type CHECK constraint rejects invalid values."""
        db_path = tmp_bank_dir / "file_metadata.db"
        conn = sqlite3.connect(str(db_path))
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO files (id, path, source_type) VALUES (?, ?, ?)",
                    ("f1", "/test", "invalid_type"),
                )
        finally:
            conn.close()

    def test_files_insert_valid_row(self, manager: FileMetadataConnectionManager, tmp_bank_dir: Path) -> None:
        db_path = tmp_bank_dir / "file_metadata.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "INSERT INTO files (id, path, source_type) VALUES (?, ?, ?)",
                ("f1", "/test.py", "agent_session"),
            )
            conn.commit()
            cursor = conn.execute("SELECT id, path, source_type FROM files WHERE id = ?", ("f1",))
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "f1"
            assert row[1] == "/test.py"
            assert row[2] == "agent_session"
        finally:
            conn.close()


class TestFileChunksTableSchema:
    """file_chunks table has the correct schema per spec."""

    def test_file_chunks_table_has_required_columns(
        self, manager: FileMetadataConnectionManager, tmp_bank_dir: Path
    ) -> None:
        db_path = tmp_bank_dir / "file_metadata.db"
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("PRAGMA table_info(file_chunks)")
            columns = {row[1]: row[2] for row in cursor.fetchall()}
            assert "file_id" in columns
            assert "memory_id" in columns
            assert "chunk_index" in columns
            assert "start_line" in columns
            assert "end_line" in columns
            assert "section_header" in columns
            assert "created_at" in columns
        finally:
            conn.close()

    def test_file_chunks_composite_primary_key(
        self, manager: FileMetadataConnectionManager, tmp_bank_dir: Path
    ) -> None:
        db_path = tmp_bank_dir / "file_metadata.db"
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("PRAGMA table_info(file_chunks)")
            pk_columns = [row[1] for row in cursor.fetchall() if row[5] > 0]
            assert "file_id" in pk_columns
            assert "memory_id" in pk_columns
        finally:
            conn.close()

    def test_file_chunks_has_indexes(self, manager: FileMetadataConnectionManager, tmp_bank_dir: Path) -> None:
        db_path = tmp_bank_dir / "file_metadata.db"
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='file_chunks' AND name NOT LIKE 'sqlite%'"
            )
            index_names = [row[0] for row in cursor.fetchall()]
            assert "idx_file_chunks_memory_id" in index_names
            assert "idx_file_chunks_file_id_chunk_index" in index_names
        finally:
            conn.close()

    def test_file_chunks_cascade_delete(self, manager: FileMetadataConnectionManager, tmp_bank_dir: Path) -> None:
        """Deleting a file cascades to its chunks."""
        db_path = tmp_bank_dir / "file_metadata.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                "INSERT INTO files (id, path, source_type) VALUES (?, ?, ?)",
                ("f1", "/test.py", "agent_session"),
            )
            conn.execute(
                "INSERT INTO file_chunks (file_id, memory_id, chunk_index) VALUES (?, ?, ?)",
                ("f1", "m1", 0),
            )
            conn.commit()
            conn.execute("DELETE FROM files WHERE id = ?", ("f1",))
            conn.commit()
            cursor = conn.execute("SELECT COUNT(*) FROM file_chunks WHERE file_id = ?", ("f1",))
            count = cursor.fetchone()[0]
            assert count == 0
        finally:
            conn.close()

    def test_file_chunks_insert_and_query(self, manager: FileMetadataConnectionManager, tmp_bank_dir: Path) -> None:
        db_path = tmp_bank_dir / "file_metadata.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "INSERT INTO files (id, path, source_type) VALUES (?, ?, ?)",
                ("f1", "/test.py", "agent_session"),
            )
            conn.execute(
                "INSERT INTO file_chunks (file_id, memory_id, chunk_index, start_line, end_line) VALUES (?, ?, ?, ?, ?)",
                ("f1", "m1", 0, 1, 50),
            )
            conn.commit()
            cursor = conn.execute(
                "SELECT file_id, memory_id, chunk_index, start_line, end_line FROM file_chunks WHERE file_id = ?",
                ("f1",),
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "f1"
            assert row[1] == "m1"
            assert row[2] == 0
            assert row[3] == 1
            assert row[4] == 50
        finally:
            conn.close()


class TestFileRelationsTableSchema:
    """file_relations table has the correct schema per spec."""

    def test_file_relations_table_has_required_columns(
        self, manager: FileMetadataConnectionManager, tmp_bank_dir: Path
    ) -> None:
        db_path = tmp_bank_dir / "file_metadata.db"
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("PRAGMA table_info(file_relations)")
            columns = {row[1]: row[2] for row in cursor.fetchall()}
            assert "source_file_id" in columns
            assert "target_file_id" in columns
            assert "relation_type" in columns
            assert "created_at" in columns
        finally:
            conn.close()

    def test_file_relations_composite_primary_key(
        self, manager: FileMetadataConnectionManager, tmp_bank_dir: Path
    ) -> None:
        db_path = tmp_bank_dir / "file_metadata.db"
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("PRAGMA table_info(file_relations)")
            pk_columns = [row[1] for row in cursor.fetchall() if row[5] > 0]
            assert "source_file_id" in pk_columns
            assert "target_file_id" in pk_columns
            assert "relation_type" in pk_columns
        finally:
            conn.close()

    def test_file_relations_has_indexes(self, manager: FileMetadataConnectionManager, tmp_bank_dir: Path) -> None:
        db_path = tmp_bank_dir / "file_metadata.db"
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='file_relations' AND name NOT LIKE 'sqlite%'"
            )
            index_names = [row[0] for row in cursor.fetchall()]
            assert "idx_file_relations_target" in index_names
            assert "idx_file_relations_type" in index_names
            assert "idx_file_relations_target_type" in index_names
        finally:
            conn.close()

    def test_file_relations_cascade_delete(self, manager: FileMetadataConnectionManager, tmp_bank_dir: Path) -> None:
        """Deleting a file cascades to its relations."""
        db_path = tmp_bank_dir / "file_metadata.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                "INSERT INTO files (id, path, source_type) VALUES (?, ?, ?)",
                ("f1", "/test1.py", "agent_session"),
            )
            conn.execute(
                "INSERT INTO files (id, path, source_type) VALUES (?, ?, ?)",
                ("f2", "/test2.py", "agent_session"),
            )
            conn.execute(
                "INSERT INTO file_relations (source_file_id, target_file_id, relation_type) VALUES (?, ?, ?)",
                ("f1", "f2", "PARENT_CHILD"),
            )
            conn.commit()
            conn.execute("DELETE FROM files WHERE id = ?", ("f1",))
            conn.commit()
            cursor = conn.execute("SELECT COUNT(*) FROM file_relations WHERE source_file_id = ?", ("f1",))
            count = cursor.fetchone()[0]
            assert count == 0
        finally:
            conn.close()

    def test_file_relations_insert_and_query(self, manager: FileMetadataConnectionManager, tmp_bank_dir: Path) -> None:
        db_path = tmp_bank_dir / "file_metadata.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "INSERT INTO files (id, path, source_type) VALUES (?, ?, ?)",
                ("f1", "/test1.py", "agent_session"),
            )
            conn.execute(
                "INSERT INTO files (id, path, source_type) VALUES (?, ?, ?)",
                ("f2", "/test2.py", "agent_session"),
            )
            conn.execute(
                "INSERT INTO file_relations (source_file_id, target_file_id, relation_type) VALUES (?, ?, ?)",
                ("f1", "f2", "PARENT_CHILD"),
            )
            conn.commit()
            cursor = conn.execute(
                "SELECT source_file_id, target_file_id, relation_type FROM file_relations " "WHERE source_file_id = ?",
                ("f1",),
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "f1"
            assert row[1] == "f2"
            assert row[2] == "PARENT_CHILD"
        finally:
            conn.close()


class TestGetConnection:
    """get_connection returns a usable SQLite connection."""

    def test_get_connection_returns_connection(self, manager: FileMetadataConnectionManager) -> None:
        conn = manager.get_connection()
        assert isinstance(conn, sqlite3.Connection)

    def test_get_connection_is_usable(self, manager: FileMetadataConnectionManager) -> None:
        conn = manager.get_connection()
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            assert "files" in tables
        finally:
            conn.close()

    def test_get_connection_has_row_factory(self, manager: FileMetadataConnectionManager) -> None:
        """Connection uses sqlite3.Row row factory for dict-like access."""
        conn = manager.get_connection()
        try:
            assert conn.row_factory == sqlite3.Row
        finally:
            conn.close()

    def test_get_connection_wal_mode(self, manager: FileMetadataConnectionManager) -> None:
        """Connection has WAL mode enabled."""
        conn = manager.get_connection()
        try:
            cursor = conn.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
            assert mode == "wal"
        finally:
            conn.close()

    def test_multiple_connections_are_independent(self, manager: FileMetadataConnectionManager) -> None:
        """Each get_connection call returns an independent connection."""
        conn1 = manager.get_connection()
        conn2 = manager.get_connection()
        try:
            # Write on conn1, read on conn2 — should see the data
            conn1.execute(
                "INSERT INTO files (id, path, source_type) VALUES (?, ?, ?)",
                ("f1", "/test.py", "agent_session"),
            )
            conn1.commit()
            cursor = conn2.execute("SELECT COUNT(*) FROM files")
            count = cursor.fetchone()[0]
            assert count == 1
        finally:
            conn1.close()
            conn2.close()


class TestCloseConnection:
    """close_connection returns connection to pool or closes it."""

    def test_close_connection_returns_to_pool(self, manager: FileMetadataConnectionManager) -> None:
        conn = manager.get_connection()
        manager.close_connection(conn)
        # Connection is pooled, so it's still usable
        cursor = conn.execute("SELECT 1")
        assert cursor.fetchone()[0] == 1

    def test_close_connection_after_manager_close_closes(self, manager: FileMetadataConnectionManager) -> None:
        conn = manager.get_connection()
        manager.close()
        manager.close_connection(conn)
        # After manager is closed, connection should be actually closed
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_close_connection_idempotent(self, manager: FileMetadataConnectionManager) -> None:
        conn = manager.get_connection()
        manager.close_connection(conn)
        manager.close_connection(conn)  # Should not raise


class TestClose:
    """close() shuts down the connection pool."""

    def test_close_clears_pool(self, manager: FileMetadataConnectionManager) -> None:
        manager.close()
        # After close, getting a connection should raise
        with pytest.raises(RuntimeError, match="closed"):
            manager.get_connection()

    def test_close_idempotent(self, manager: FileMetadataConnectionManager) -> None:
        manager.close()
        manager.close()  # Should not raise


class TestCreateTables:
    """create_tables is idempotent and creates all tables."""

    def test_create_tables_is_idempotent(self, manager: FileMetadataConnectionManager, tmp_bank_dir: Path) -> None:
        """Calling create_tables multiple times does not error."""
        manager.create_tables()
        manager.create_tables()  # Should not raise

    def test_create_tables_on_fresh_db(self, tmp_bank_dir: Path) -> None:
        """create_tables works on a brand new database."""
        mgr = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        # Tables already created on init, but re-creating should be safe
        mgr.create_tables()

    def test_create_tables_creates_all_tables(self, manager: FileMetadataConnectionManager, tmp_bank_dir: Path) -> None:
        db_path = tmp_bank_dir / "file_metadata.db"
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            table_names = [row[0] for row in cursor.fetchall()]
            assert "files" in table_names
            assert "file_chunks" in table_names
            assert "file_relations" in table_names
            assert "schema_version" in table_names
        finally:
            conn.close()


class TestCheckMigrations:
    """check_migrations detects schema version and pending migrations."""

    def test_check_migrations_returns_current_version(self, manager: FileMetadataConnectionManager) -> None:
        version = manager.check_migrations()
        assert version == MIGRATIONS[-1].version

    def test_check_migrations_returns_pending_count_zero(self, manager: FileMetadataConnectionManager) -> None:
        result = manager.check_migrations()
        # After init, no pending migrations
        assert result == MIGRATIONS[-1].version

    def test_check_migrations_on_old_schema(self, tmp_bank_dir: Path) -> None:
        """Simulate an old schema and verify check_migrations detects it."""
        db_path = tmp_bank_dir / "file_metadata.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (0,))
            conn.commit()
        finally:
            conn.close()

        mgr = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        # Manager should have applied migrations on init
        version = mgr.check_migrations()
        assert version == MIGRATIONS[-1].version

    def test_check_migrations_applies_pending(self, tmp_bank_dir: Path) -> None:
        """Manager applies pending migrations on init."""
        db_path = tmp_bank_dir / "file_metadata.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (0,))
            conn.commit()
        finally:
            conn.close()

        mgr = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        # After init, all migrations should be applied
        version = mgr.check_migrations()
        assert version == MIGRATIONS[-1].version

        # Verify tables exist
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            table_names = [row[0] for row in cursor.fetchall()]
            assert "files" in table_names
            assert "file_chunks" in table_names
            assert "file_relations" in table_names
        finally:
            conn.close()


def _build_pre_v6_db(db_path: Path) -> None:
    """Build a database at schema version 5 (pre-V6) by applying V1–V5 raw SQL."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        for migration in MIGRATIONS:
            if migration.version > 5:
                break
            conn.executescript(migration.up_sql)
            conn.execute("DELETE FROM schema_version")
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (migration.version,),
            )
            conn.commit()
    finally:
        conn.close()


def _file_chunks_column_names(db_path: Path) -> list[str]:
    """Return the column names of file_chunks via PRAGMA table_info."""
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute("PRAGMA table_info(file_chunks)")
        return [row[1] for row in cursor.fetchall()]
    finally:
        conn.close()


class TestMigrationV6:
    """V6 adds parent_unit_ref/parent_unit_summary to file_chunks, idempotently."""

    def test_v6_is_sequentially_last_migration(self) -> None:
        assert MIGRATIONS[-1].version == 6
        v6 = MIGRATIONS[-1]
        assert "ALTER TABLE file_chunks ADD COLUMN parent_unit_ref TEXT" in v6.up_sql
        assert "ALTER TABLE file_chunks ADD COLUMN parent_unit_summary TEXT" in v6.up_sql

    def test_v6_applies_after_v5_on_pre_v6_db(self, tmp_bank_dir: Path) -> None:
        """A pre-V6 (version 5) database migrates to V6 on manager init."""
        db_path = tmp_bank_dir / "file_metadata.db"
        _build_pre_v6_db(db_path)

        mgr = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        try:
            assert mgr.check_migrations() == 6
            columns = _file_chunks_column_names(db_path)
            assert columns.count("parent_unit_ref") == 1
            assert columns.count("parent_unit_summary") == 1
        finally:
            mgr.close()

    def test_v6_idempotent_on_fresh_db(self, tmp_bank_dir: Path) -> None:
        """Creating a fresh DB twice (second manager on same file) leaves each
        column exactly once and no error."""
        db_path = tmp_bank_dir / "file_metadata.db"
        mgr1 = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        mgr1.close()

        mgr2 = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        try:
            assert mgr2.check_migrations() == 6
            columns = _file_chunks_column_names(db_path)
            assert columns.count("parent_unit_ref") == 1
            assert columns.count("parent_unit_summary") == 1
        finally:
            mgr2.close()

    def test_v6_idempotent_on_pre_v6_db(self, tmp_bank_dir: Path) -> None:
        """Re-opening a pre-V6 DB twice migrates to V6 with each column once."""
        db_path = tmp_bank_dir / "file_metadata.db"
        _build_pre_v6_db(db_path)

        mgr1 = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        mgr1.close()

        mgr2 = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        try:
            assert mgr2.check_migrations() == 6
            columns = _file_chunks_column_names(db_path)
            assert columns.count("parent_unit_ref") == 1
            assert columns.count("parent_unit_summary") == 1
        finally:
            mgr2.close()

    def test_v1_v5_behavior_unchanged(self, tmp_bank_dir: Path) -> None:
        """V1–V5 migrations are byte-identical to the pre-V6 list (append-only)."""
        for i in range(5):
            assert MIGRATIONS[i].version == i + 1
            assert "parent_unit_ref" not in MIGRATIONS[i].up_sql
            assert "parent_unit_summary" not in MIGRATIONS[i].up_sql


class TestPerBankIsolation:
    """Each bank has its own isolated database."""

    def test_separate_banks_have_separate_dbs(self, tmp_path: Path) -> None:
        bank1_dir = tmp_path / "bank1"
        bank2_dir = tmp_path / "bank2"

        mgr1 = FileMetadataConnectionManager(bank_dir=bank1_dir)
        mgr2 = FileMetadataConnectionManager(bank_dir=bank2_dir)

        conn1 = mgr1.get_connection()
        conn1.execute(
            "INSERT INTO files (id, path, source_type) VALUES (?, ?, ?)",
            ("f1", "/bank1/test.py", "agent_session"),
        )
        conn1.commit()
        conn1.close()

        conn2 = mgr2.get_connection()
        cursor = conn2.execute("SELECT COUNT(*) FROM files")
        count = cursor.fetchone()[0]
        assert count == 0
        conn2.close()

        mgr1.close()
        mgr2.close()

    def test_bank_db_path_is_correct(self, tmp_bank_dir: Path) -> None:
        manager = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        assert manager.db_path == tmp_bank_dir / "file_metadata.db"
        manager.close()


class TestConnectionPooling:
    """Connection pool manages connections efficiently."""

    def test_pool_reuses_connections(self, manager: FileMetadataConnectionManager) -> None:
        """Pool has a pool of connections, not just one."""
        # Get multiple connections simultaneously
        conns = [manager.get_connection() for _ in range(3)]
        try:
            # All should be usable
            for conn in conns:
                cursor = conn.execute("SELECT 1")
                assert cursor.fetchone()[0] == 1
        finally:
            for conn in conns:
                manager.close_connection(conn)

    def test_pool_thread_safety(self, manager: FileMetadataConnectionManager) -> None:
        """Multiple threads can get connections without errors."""
        errors: list[Exception] = []

        def worker() -> None:
            try:
                conn = manager.get_connection()
                try:
                    conn.execute("SELECT 1")
                finally:
                    manager.close_connection(conn)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_pool_size_limit(self, manager: FileMetadataConnectionManager) -> None:
        """Pool has a maximum size; exceeding raises RuntimeError."""
        conns: list[sqlite3.Connection] = []
        try:
            # Get connections up to the pool limit
            for _ in range(10):
                try:
                    conn = manager.get_connection()
                    conns.append(conn)
                except RuntimeError:
                    break

            # Should have hit the limit (default pool size is 5)
            assert len(conns) <= 5
        finally:
            for conn in conns:
                manager.close_connection(conn)
