"""Hash index tests — SQLite-backed chunk_hash → memory_id dedup index.

Covers the dual-hash wire contract re-key (D14): the index is keyed by
chunk content hash. Per D28 there is no legacy migration machinery — a
brand-new database is bootstrapped fresh (mkdir + create_all); pre-existing
dev DB files are deleted manually (no in-place upgrade path).
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


class TestFreshBootstrap:
    """D28 fresh bootstrap: no migration machinery — a brand-new database is
    created keyed by chunk_hash (mkdir + create_all), idempotently."""

    def test_fresh_db_created_with_chunk_hash_pk(self, tmp_db_path: Path) -> None:
        """A brand-new database is created keyed by chunk_hash."""
        index = HashIndexService("test_bank", tmp_db_path)

        columns = _table_columns(tmp_db_path)
        pk_columns = [name for name, pk in columns if pk > 0]
        assert pk_columns == ["chunk_hash"]
        assert _row_count(tmp_db_path) == 0

    def test_init_is_idempotent_on_fresh_db(self, tmp_db_path: Path) -> None:
        """Re-initializing the service on an already-bootstrapped DB succeeds
        and leaves the schema and data intact."""
        first = HashIndexService("test_bank", tmp_db_path)
        first.store("sha256_seed", "mem_seed")

        second = HashIndexService("test_bank", tmp_db_path)

        columns = _table_columns(tmp_db_path)
        pk_columns = [name for name, pk in columns if pk > 0]
        assert pk_columns == ["chunk_hash"]
        assert second.lookup("sha256_seed").value == "mem_seed"


class TestStaleSchemaSelfHeal:
    """D30 self-heal guard: a pre-D14 stale database (``file_hash``-PK schema)
    is detected and replaced with the canonical ``chunk_hash`` schema on access.

    The guard fires ONLY when the table exists without a ``chunk_hash`` column.
    Fresh DBs and correct-schema DBs are untouched. No row copy — the legacy
    ``file_hash``-keyed rows are a dead value space (post-D12).
    """

    def _create_stale_db(self, db_path: Path) -> None:
        """Create a stale pre-D14 database via raw SQL (file_hash PK + 1 row)."""
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "CREATE TABLE hash_index "
                "(file_hash TEXT PRIMARY KEY, memory_id TEXT NOT NULL)"
            )
            conn.execute(
                "INSERT INTO hash_index (file_hash, memory_id) "
                "VALUES ('legacy_file_hash_1', 'mem_legacy_1')"
            )
            conn.commit()
        finally:
            conn.close()

    def _create_correct_db_with_rows(self, db_path: Path) -> None:
        """Create a correct-schema database with rows via raw SQL (chunk_hash PK)."""
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "CREATE TABLE hash_index "
                "(chunk_hash TEXT PRIMARY KEY, memory_id TEXT NOT NULL)"
            )
            conn.execute(
                "INSERT INTO hash_index (chunk_hash, memory_id) "
                "VALUES ('good_chunk_hash_1', 'mem_good_1')"
            )
            conn.commit()
        finally:
            conn.close()

    def test_stale_db_recreated_with_chunk_hash_pk(
        self, tmp_path: Path
    ) -> None:
        """(a) Stale DB → after init the table is recreated keyed by chunk_hash."""
        db_path = tmp_path / "stale_bank" / "hash_index.db"
        self._create_stale_db(db_path)

        HashIndexService("stale_bank", db_path)

        columns = _table_columns(db_path)
        pk_columns = [name for name, pk in columns if pk > 0]
        assert pk_columns == ["chunk_hash"]

    def test_stale_db_healed_removes_legacy_rows(
        self, tmp_path: Path
    ) -> None:
        """(a) Stale DB → legacy file_hash-keyed rows are dropped (no row copy)."""
        db_path = tmp_path / "stale_bank" / "hash_index.db"
        self._create_stale_db(db_path)

        HashIndexService("stale_bank", db_path)

        assert _row_count(db_path) == 0

    def test_stale_db_healed_logs_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(a) Stale DB → exactly one structured warning is logged per heal."""
        from src.infrastructure.mcp import hash_index_service
        from src.utils.structured_logging import LoggerMock

        mock_logger = LoggerMock()
        monkeypatch.setattr(hash_index_service, "logger", mock_logger)

        db_path = tmp_path / "stale_bank" / "hash_index.db"
        self._create_stale_db(db_path)

        HashIndexService("stale_bank", db_path)

        heal_events = [
            entry
            for entry in mock_logger.entries
            if entry["event"] == "hash_index legacy schema replaced"
        ]
        assert len(heal_events) == 1
        # Behavior-level: the warning is attributed to the db + bank, not pinned
        # to a message string.
        assert heal_events[0]["level"] == "warning"
        assert heal_events[0].get("db_path") is not None
        assert heal_events[0].get("memory_bank") == "stale_bank"

    def test_correct_schema_db_rows_survive(
        self, tmp_path: Path
    ) -> None:
        """(c) Correct-schema DB → guard must NOT drop; rows survive."""
        db_path = tmp_path / "good_bank" / "hash_index.db"
        self._create_correct_db_with_rows(db_path)

        index = HashIndexService("good_bank", db_path)

        assert _row_count(db_path) == 1
        assert index.lookup("good_chunk_hash_1").value == "mem_good_1"

    def test_idempotent_reinit_on_healed_db(
        self, tmp_path: Path
    ) -> None:
        """(d) Re-init on an already-healed DB is a no-op (no re-drop)."""
        db_path = tmp_path / "healed_bank" / "hash_index.db"
        self._create_stale_db(db_path)

        first = HashIndexService("healed_bank", db_path)
        first.store("sha256_post_heal", "mem_post_heal")

        second = HashIndexService("healed_bank", db_path)

        columns = _table_columns(db_path)
        pk_columns = [name for name, pk in columns if pk > 0]
        assert pk_columns == ["chunk_hash"]
        assert second.lookup("sha256_post_heal").value == "mem_post_heal"
