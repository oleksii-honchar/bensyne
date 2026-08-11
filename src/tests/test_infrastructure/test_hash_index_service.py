"""HashIndexService infrastructure wrapper tests — Result-returning wrapper.

Verifies:
- HashIndexService wraps HashIndex with Result-returning methods
- All exceptions caught and converted to Result.ko with HASH_INDEX_ERROR
- store/lookup/remove round-trip correctly
- lookup returns None for non-existent hash
- remove returns None when memory_id not found
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from src.domain.result import ErrorWithDetails, Result
from src.infrastructure.hash_index_service import HashIndexService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Return a path inside a temp directory for the SQLite database."""
    return tmp_path / "test_bank" / "hash_index.db"


@pytest.fixture
def service(tmp_db_path: Path) -> HashIndexService:
    """Create a HashIndexService backed by a temporary SQLite database."""
    return HashIndexService(memory_bank="test_bank", db_path=tmp_db_path)


@pytest.fixture
def mock_hash_index() -> MagicMock:
    """Create a mock HashIndex instance."""
    mock = MagicMock()
    mock.lookup.return_value = "mem_001"
    mock.store.return_value = None
    mock.remove.return_value = "abc123"
    return mock


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestHashIndexServiceConstructor:
    """HashIndexService initializes with memory_bank and creates HashIndex."""

    def test_stores_memory_bank(self, tmp_db_path: Path) -> None:
        """memory_bank is stored as an attribute."""
        svc = HashIndexService(memory_bank="my_bank", db_path=tmp_db_path)
        assert svc.memory_bank == "my_bank"

    def test_creates_hash_index(self, tmp_db_path: Path) -> None:
        """HashIndex is created during construction."""
        with patch("src.infrastructure.hash_index_service.HashIndex") as mock_cls:
            HashIndexService(memory_bank="test", db_path=tmp_db_path)
        mock_cls.assert_called_once_with(tmp_db_path)


# ---------------------------------------------------------------------------
# store
# ---------------------------------------------------------------------------


class TestHashIndexServiceStore:
    """store() returns Result.ok on success, Result.ko on error."""

    def test_returns_result_ok_on_success(self, service: HashIndexService) -> None:
        """store() returns Result.ok after successful store."""
        result = service.store("abc123", "mem_001")

        assert result.is_ok

    def test_delegates_to_hash_index_store(self, service: HashIndexService) -> None:
        """store() delegates to the underlying HashIndex."""
        service.store("abc123", "mem_001")
        # Verify the value was actually stored by looking it up
        lookup_result = service.lookup("abc123")
        assert lookup_result.is_ok
        assert lookup_result.value == "mem_001"

    def test_returns_result_ko_on_exception(self, mock_hash_index: MagicMock) -> None:
        """store() returns Result.ko with HASH_INDEX_ERROR when HashIndex raises."""
        mock_hash_index.store.side_effect = RuntimeError("disk full")

        with patch("src.infrastructure.hash_index_service.HashIndex", return_value=mock_hash_index):
            svc = HashIndexService(memory_bank="test", db_path=Path("/tmp/test.db"))

        result = svc.store("abc123", "mem_001")

        assert result.is_ko
        errors = result.get_errors()
        assert len(errors) == 1
        assert errors[0].error_code == "HASH_INDEX_ERROR"


# ---------------------------------------------------------------------------
# lookup
# ---------------------------------------------------------------------------


class TestHashIndexServiceLookup:
    """lookup() returns Result.ok with memory_id or None, Result.ko on error."""

    def test_returns_memory_id_for_existing_hash(self, service: HashIndexService) -> None:
        """lookup() returns Result.ok with memory_id when hash exists."""
        service.store("abc123", "mem_001")

        result = service.lookup("abc123")

        assert result.is_ok
        assert result.value == "mem_001"

    def test_returns_none_for_non_existent_hash(self, service: HashIndexService) -> None:
        """lookup() returns Result.ok with None when hash does not exist."""
        result = service.lookup("nonexistent")

        assert result.is_ok
        assert result.value is None

    def test_returns_result_ko_on_exception(self, mock_hash_index: MagicMock) -> None:
        """lookup() returns Result.ko with HASH_INDEX_ERROR when HashIndex raises."""
        mock_hash_index.lookup.side_effect = sqlite3.OperationalError("db locked")

        with patch("src.infrastructure.hash_index_service.HashIndex", return_value=mock_hash_index):
            svc = HashIndexService(memory_bank="test", db_path=Path("/tmp/test.db"))

        result = svc.lookup("abc123")

        assert result.is_ko
        errors = result.get_errors()
        assert errors[0].error_code == "HASH_INDEX_ERROR"


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------


class TestHashIndexServiceRemove:
    """remove() returns Result.ok with removed hash or None, Result.ko on error."""

    def test_returns_removed_hash_on_success(self, service: HashIndexService) -> None:
        """remove() returns Result.ok with the removed hash value."""
        service.store("hash_del", "mem_del")

        result = service.remove("mem_del")

        assert result.is_ok
        assert result.value == "hash_del"

    def test_returns_none_when_memory_id_not_found(self, service: HashIndexService) -> None:
        """remove() returns Result.ok with None when memory_id not found."""
        result = service.remove("mem_not_found")

        assert result.is_ok
        assert result.value is None

    def test_returns_result_ko_on_exception(self, mock_hash_index: MagicMock) -> None:
        """remove() returns Result.ko with HASH_INDEX_ERROR when HashIndex raises."""
        mock_hash_index.remove.side_effect = RuntimeError("index corrupted")

        with patch("src.infrastructure.hash_index_service.HashIndex", return_value=mock_hash_index):
            svc = HashIndexService(memory_bank="test", db_path=Path("/tmp/test.db"))

        result = svc.remove("mem_001")

        assert result.is_ko
        errors = result.get_errors()
        assert errors[0].error_code == "HASH_INDEX_ERROR"


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


class TestHashIndexServiceRoundTrip:
    """End-to-end round-trip: store then lookup, store then remove."""

    def test_store_and_lookup_round_trip(self, service: HashIndexService) -> None:
        """store() and lookup() work together in a round-trip."""
        store_result = service.store("abc123def456", "mem_roundtrip")
        assert store_result.is_ok

        lookup_result = service.lookup("abc123def456")

        assert lookup_result.is_ok
        assert lookup_result.value == "mem_roundtrip"

    def test_store_remove_and_lookup_none(self, service: HashIndexService) -> None:
        """After remove(), lookup() returns None for the removed hash."""
        service.store("hash_rt", "mem_rt")

        remove_result = service.remove("mem_rt")
        assert remove_result.is_ok
        assert remove_result.value == "hash_rt"

        lookup_result = service.lookup("hash_rt")

        assert lookup_result.is_ok
        assert lookup_result.value is None
