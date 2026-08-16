"""Hash index tests — SQLite-backed file_hash → memory_id dedup index."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Generator

import pytest

from src.infrastructure.mcp.hash_index_service import HashIndexService


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Return a path inside a temp directory for the SQLite database."""
    return tmp_path / "test_bank" / "hash_index.db"


@pytest.fixture
def index(tmp_db_path: Path) -> Generator[HashIndexService, None, None]:
    """Create a HashIndexService backed by a temporary SQLite database."""
    yield HashIndexService("test_bank", tmp_db_path)


class TestLookup:
    """lookup returns memory_id if hash exists, None otherwise."""

    def test_lookup_returns_none_for_non_existent_hash(self, index: HashIndexService) -> None:
        result = index.lookup("abc123")
        assert result.is_ok
        assert result.value is None

    def test_lookup_returns_memory_id_after_store(self, index: HashIndexService) -> None:
        index.store("abc123", "mem_001")
        result = index.lookup("abc123")
        assert result.is_ok
        assert result.value == "mem_001"

    def test_lookup_returns_none_for_different_hash(self, index: HashIndexService) -> None:
        index.store("abc123", "mem_001")
        result = index.lookup("xyz789")
        assert result.is_ok
        assert result.value is None

    def test_lookup_returns_latest_after_replace(self, index: HashIndexService) -> None:
        index.store("abc123", "mem_001")
        index.store("abc123", "mem_002")
        result = index.lookup("abc123")
        assert result.is_ok
        assert result.value == "mem_002"


class TestStore:
    """store inserts or replaces hash mapping."""

    def test_store_creates_entry(self, index: HashIndexService) -> None:
        index.store("hash_a", "mem_100")
        result = index.lookup("hash_a")
        assert result.is_ok
        assert result.value == "mem_100"

    def test_store_replaces_existing(self, index: HashIndexService) -> None:
        index.store("hash_a", "mem_100")
        index.store("hash_a", "mem_200")
        result = index.lookup("hash_a")
        assert result.is_ok
        assert result.value == "mem_200"

    def test_store_multiple_hashes(self, index: HashIndexService) -> None:
        index.store("hash_1", "mem_1")
        index.store("hash_2", "mem_2")
        result1 = index.lookup("hash_1")
        result2 = index.lookup("hash_2")
        assert result1.is_ok and result1.value == "mem_1"
        assert result2.is_ok and result2.value == "mem_2"


class TestRemove:
    """remove finds and removes the hash entry for a given memory_id."""

    def test_remove_returns_hash_and_clears_entry(self, index: HashIndexService) -> None:
        index.store("hash_del", "mem_del")
        removed_result = index.remove("mem_del")
        assert removed_result.is_ok
        assert removed_result.value == "hash_del"
        lookup_result = index.lookup("hash_del")
        assert lookup_result.is_ok
        assert lookup_result.value is None

    def test_remove_returns_none_when_memory_id_not_found(self, index: HashIndexService) -> None:
        index.store("hash_a", "mem_1")
        removed_result = index.remove("mem_not_found")
        assert removed_result.is_ok
        assert removed_result.value is None

    def test_remove_does_not_affect_other_entries(self, index: HashIndexService) -> None:
        index.store("hash_a", "mem_a")
        index.store("hash_b", "mem_b")
        removed_result = index.remove("mem_a")
        assert removed_result.is_ok
        assert removed_result.value == "hash_a"
        lookup_result = index.lookup("hash_b")
        assert lookup_result.is_ok
        assert lookup_result.value == "mem_b"

    def test_remove_on_empty_index(self, index: HashIndexService) -> None:
        removed_result = index.remove("mem_none")
        assert removed_result.is_ok
        assert removed_result.value is None


class TestLazyCreation:
    """Database is created lazily on first use; directory created if needed."""

    def test_db_file_created_on_instantiation(self, tmp_db_path: Path) -> None:
        assert not tmp_db_path.exists()
        HashIndexService("test_bank", tmp_db_path)
        assert tmp_db_path.exists()

    def test_parent_directory_created_if_missing(self, tmp_path: Path) -> None:
        deep_path = tmp_path / "a" / "b" / "c" / "hash_index.db"
        assert not deep_path.parent.exists()
        HashIndexService("deep_bank", deep_path)
        assert deep_path.exists()
        assert deep_path.parent.exists()

    def test_table_created_on_instantiation(self, tmp_db_path: Path) -> None:
        HashIndexService("test_bank", tmp_db_path)
        conn = sqlite3.connect(str(tmp_db_path))
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hash_index'")
            assert cursor.fetchone() is not None
        finally:
            conn.close()


class TestWALMode:
    """Thread-safe operations via WAL mode."""

    def test_wal_mode_enabled(self, index: HashIndexService, tmp_db_path: Path) -> None:
        conn = sqlite3.connect(str(tmp_db_path))
        try:
            cursor = conn.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
            assert mode == "wal"
        finally:
            conn.close()
