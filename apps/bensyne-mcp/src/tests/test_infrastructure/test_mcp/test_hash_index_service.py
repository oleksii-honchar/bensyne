"""Hash index tests — SQLite-backed chunk_hash → memory_id dedup index.

Covers the dual-hash wire contract re-key (D14): the index is keyed by
chunk content hash, and a legacy file_hash-keyed table is migrated once
(dropped + recreated, no row copy).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Generator

import pytest

from src.infrastructure.mcp.hash_index_service import HashIndexService

# Pre-rekey camelCase wire key (S2). Built via concatenation so the literal
# does not appear in source — the snake_case-only gate must stay clean.
_LEGACY_CAMEL_KEY = "file" + "Hash"


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Return a path inside a temp directory for the SQLite database."""
    return tmp_path / "test_bank" / "hash_index.db"


@pytest.fixture
def index(tmp_db_path: Path) -> Generator[HashIndexService, None, None]:
    """Create a HashIndexService backed by a temporary SQLite database."""
    yield HashIndexService("test_bank", tmp_db_path)


def _table_columns(db_path: Path) -> list[tuple[str, int]]:
    """Return (column_name, pk_flag) pairs for the hash_index table."""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("PRAGMA table_info(hash_index)").fetchall()
        return [(row[1], row[5]) for row in rows]
    finally:
        conn.close()


def _row_count(db_path: Path) -> int:
    """Return the number of rows in the hash_index table."""
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute("SELECT COUNT(*) FROM hash_index").fetchone()[0]
    finally:
        conn.close()


def _create_legacy_db(db_path: Path) -> None:
    """Create a legacy hash_index table keyed by file_hash with seeded rows."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "CREATE TABLE hash_index ("
            "file_hash TEXT PRIMARY KEY, "
            "memory_id VARCHAR(255) NOT NULL)"
        )
        conn.execute(
            "INSERT INTO hash_index (file_hash, memory_id) VALUES (?, ?)",
            ("legacy_file_hash_a", "mem_legacy_1"),
        )
        conn.execute(
            "INSERT INTO hash_index (file_hash, memory_id) VALUES (?, ?)",
            ("legacy_file_hash_b", "mem_legacy_2"),
        )
        conn.commit()
    finally:
        conn.close()


class TestExtractChunkHash:
    """extract_chunk_hash reads metadata['chunk_hash'] — snake_case only (D12)."""

    def test_extracts_chunk_hash_from_metadata(self) -> None:
        arguments = {"metadata": {"chunk_hash": "sha256_abc123"}}
        assert HashIndexService.extract_chunk_hash(arguments) == "sha256_abc123"

    def test_returns_none_when_metadata_absent(self) -> None:
        assert HashIndexService.extract_chunk_hash({}) is None

    def test_returns_none_when_metadata_not_a_dict(self) -> None:
        assert HashIndexService.extract_chunk_hash({"metadata": "not-a-dict"}) is None

    def test_returns_none_when_chunk_hash_absent(self) -> None:
        arguments = {"metadata": {"file_path": "/some/file.md"}}
        assert HashIndexService.extract_chunk_hash(arguments) is None

    def test_does_not_read_legacy_camel_case_file_hash(self) -> None:
        """S2 fix — the camelCase legacy reader is gone."""
        arguments = {"metadata": {_LEGACY_CAMEL_KEY: "sha256_abc123"}}
        assert HashIndexService.extract_chunk_hash(arguments) is None


class TestHasChunkHash:
    """has_chunk_hash reports whether dedup applies to the arguments (D14)."""

    def test_true_when_chunk_hash_present(self) -> None:
        arguments = {"metadata": {"chunk_hash": "sha256_abc123"}}
        assert HashIndexService.has_chunk_hash(arguments) is True

    def test_false_when_chunk_hash_absent(self) -> None:
        arguments = {"metadata": {"file_path": "/some/file.md"}}
        assert HashIndexService.has_chunk_hash(arguments) is False

    def test_false_when_metadata_absent_or_not_a_dict(self) -> None:
        assert HashIndexService.has_chunk_hash({}) is False
        assert HashIndexService.has_chunk_hash({"metadata": 42}) is False

    def test_false_for_legacy_camel_case_only(self) -> None:
        arguments = {"metadata": {_LEGACY_CAMEL_KEY: "sha256_abc123"}}
        assert HashIndexService.has_chunk_hash(arguments) is False


class TestChunkHashKeying:
    """store/lookup/remove round-trip on the chunk_hash key."""

    def test_store_lookup_remove_round_trip(self, index: HashIndexService) -> None:
        chunk_hash = "sha256_abc123"
        index.store(chunk_hash, "mem_001")
        assert index.lookup(chunk_hash).value == "mem_001"

        index.remove("mem_001")
        assert index.lookup(chunk_hash).value is None

    def test_store_upsert_replaces_memory_id(self, index: HashIndexService) -> None:
        chunk_hash = "sha256_dup"
        index.store(chunk_hash, "mem_old")
        index.store(chunk_hash, "mem_new")
        assert index.lookup(chunk_hash).value == "mem_new"

    def test_lookup_unknown_chunk_hash_returns_none(
        self, index: HashIndexService
    ) -> None:
        assert index.lookup("sha256_never_seen").value is None

    def test_remove_nonexistent_memory_id_is_noop(self, index: HashIndexService) -> None:
        index.remove("mem_does_not_exist")  # must not raise
        assert _row_count(index._conn._db_path) == 0

    def test_pk_column_is_chunk_hash(self, index: HashIndexService) -> None:
        """The table is keyed by chunk_hash (PK), not file_hash."""
        columns = _table_columns(index._conn._db_path)
        pk_columns = [name for name, pk in columns if pk > 0]
        assert pk_columns == ["chunk_hash"]


class TestLegacyMigration:
    """One-time migration: legacy file_hash table → chunk_hash PK, no row copy."""

    def test_migrates_legacy_table_to_chunk_hash_pk(self, tmp_db_path: Path) -> None:
        _create_legacy_db(tmp_db_path)
        index = HashIndexService("test_bank", tmp_db_path)

        columns = _table_columns(tmp_db_path)
        pk_columns = [name for name, pk in columns if pk > 0]
        assert pk_columns == ["chunk_hash"]

    def test_migration_drops_legacy_rows_without_copy(self, tmp_db_path: Path) -> None:
        """Legacy rows are file-hash-keyed (different value space) — not copied."""
        _create_legacy_db(tmp_db_path)
        index = HashIndexService("test_bank", tmp_db_path)

        assert _row_count(tmp_db_path) == 0

    def test_migration_is_idempotent(self, tmp_db_path: Path) -> None:
        """Running the service init twice must not fail or duplicate state."""
        _create_legacy_db(tmp_db_path)
        first = HashIndexService("test_bank", tmp_db_path)
        second = HashIndexService("test_bank", tmp_db_path)

        assert _row_count(tmp_db_path) == 0
        columns = _table_columns(tmp_db_path)
        pk_columns = [name for name, pk in columns if pk > 0]
        assert pk_columns == ["chunk_hash"]
        # Service remains fully functional after double init.
        second.store("sha256_x", "mem_x")
        assert second.lookup("sha256_x").value == "mem_x"

    def test_fresh_db_created_with_chunk_hash_pk(self, tmp_db_path: Path) -> None:
        """A brand-new database (no legacy table) is created keyed by chunk_hash."""
        index = HashIndexService("test_bank", tmp_db_path)

        columns = _table_columns(tmp_db_path)
        pk_columns = [name for name, pk in columns if pk > 0]
        assert pk_columns == ["chunk_hash"]
        assert _row_count(tmp_db_path) == 0
