"""MemoryBankRepository tests — SQLAlchemy-backed persistence for memory_banks.db.

Exercises the real repository against a tmp_path DB and proves behavioral
parity with the existing InMemoryMemoryBankRepository fake
(src/tests/test_domain/domain_test_utils.py:132-155): save/find_by_id/list/
delete with the same Result contract, plus the SQLite-specific requirements
(WAL mode, ON CONFLICT upsert, ISO-8601 UTC timestamps, memories never written).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.domain.memory_bank_aggregate import MemoryBank
from src.infrastructure.bank.memory_bank_repository import (
    MemoryBankRepository,
    memory_banks_db_path,
)
from src.tests.test_domain.domain_test_utils import a_memory, a_memory_bank


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path) -> MemoryBankRepository:
    """A MemoryBankRepository backed by a fresh tmp_path database."""
    return MemoryBankRepository(tmp_path / "memory_banks.db")


def _utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    """Build a timezone-aware UTC datetime fixture (exact round-trip storage)."""
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def _row_count(db_path: Path) -> int:
    """Count rows in the memory_banks table via raw sqlite3."""
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute("SELECT COUNT(*) FROM memory_banks").fetchone()[0]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Contract parity with InMemoryMemoryBankRepository
# ---------------------------------------------------------------------------


class TestRepositoryContract:
    """Behavioral parity: the real repository matches the fake's contract."""

    def test_save_returns_result_ok(self, repo: MemoryBankRepository) -> None:
        bank = a_memory_bank()
        result = repo.save(bank)
        assert result.is_ok is True

    def test_save_find_by_id_round_trip_preserves_all_persisted_fields(self, repo: MemoryBankRepository) -> None:
        bank = a_memory_bank(
            name="rt_bank",
            description="Round trip bank",
            status="active",
            created_at=_utc(2026, 1, 2, 3, 4, 5),
            last_accessed=_utc(2026, 2, 3, 4, 5, 6),
            memory_count=7,
        )
        assert repo.save(bank).is_ok
        result = repo.find_by_id("rt_bank")
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.name == "rt_bank"
        assert result.value.description == "Round trip bank"
        assert result.value.status == "active"
        assert result.value.created_at == _utc(2026, 1, 2, 3, 4, 5)
        assert result.value.last_accessed == _utc(2026, 2, 3, 4, 5, 6)
        assert result.value.memory_count == 7
        assert result.value.memories == []

    def test_save_twice_upserts_updates_fields_name_stays_pk(self, repo: MemoryBankRepository) -> None:
        first = a_memory_bank(name="bank1", description="one", status="registered", memory_count=0)
        assert repo.save(first).is_ok
        second = a_memory_bank(
            name="bank1",
            description="two",
            status="active",
            created_at=_utc(2026, 1, 1),
            last_accessed=_utc(2026, 3, 3),
            memory_count=5,
        )
        assert repo.save(second).is_ok

        result = repo.find_by_id("bank1")
        assert result.is_ok and result.value is not None
        assert result.value.name == "bank1"
        assert result.value.description == "two"
        assert result.value.status == "active"
        assert result.value.memory_count == 5
        assert _row_count(repo._db_path) == 1

    def test_list_returns_banks_ordered_by_name_with_empty_memories(self, repo: MemoryBankRepository) -> None:
        assert repo.save(a_memory_bank(name="z_bank", description="Z")).is_ok
        assert repo.save(a_memory_bank(name="a_bank", description="A")).is_ok
        assert repo.save(a_memory_bank(name="m_bank", description="M")).is_ok

        result = repo.list()
        assert result.is_ok is True
        assert result.value is not None
        assert [bank.name for bank in result.value] == ["a_bank", "m_bank", "z_bank"]
        assert all(bank.memories == [] for bank in result.value)

    def test_list_returns_empty_list_for_empty_db(self, repo: MemoryBankRepository) -> None:
        result = repo.list()
        assert result.is_ok is True
        assert result.value == []

    def test_find_by_id_returns_none_for_absent_bank(self, repo: MemoryBankRepository) -> None:
        result = repo.find_by_id("nonexistent")
        assert result.is_ok is True
        assert result.value is None

    def test_delete_returns_true_when_found_and_false_when_absent(self, repo: MemoryBankRepository) -> None:
        assert repo.save(a_memory_bank(name="gone", description="G")).is_ok
        assert repo.delete("gone") is True
        assert repo.find_by_id("gone").value is None
        assert repo.delete("gone") is False


# ---------------------------------------------------------------------------
# MemoryBank.of() persistence + memories ignored
# ---------------------------------------------------------------------------


class TestOfFactoryPersistence:
    """Banks produced by MemoryBank.of(...) persist their scalar fields."""

    def test_save_persists_bank_from_of_factory(self, repo: MemoryBankRepository) -> None:
        created = MemoryBank.of("of_bank", "From factory")
        assert created.is_ok and created.value is not None
        assert repo.save(created.value).is_ok

        result = repo.find_by_id("of_bank")
        assert result.is_ok and result.value is not None
        stored = result.value
        assert stored.name == "of_bank"
        assert stored.description == "From factory"
        assert stored.status == "registered"
        assert stored.memory_count == 0
        assert stored.memories == []

    def test_created_at_stored_as_iso8601_utc_string(self, repo: MemoryBankRepository) -> None:
        created = MemoryBank.of("utc_bank", "Desc")
        assert created.is_ok and created.value is not None
        assert repo.save(created.value).is_ok

        conn = sqlite3.connect(str(repo._db_path))
        try:
            raw = conn.execute("SELECT created_at FROM memory_banks WHERE name = 'utc_bank'").fetchone()[0]
        finally:
            conn.close()
        assert raw.endswith("+00:00")
        parsed = datetime.fromisoformat(raw)
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == timezone.utc.utcoffset(None)

    def test_memories_are_ignored_never_written(self, repo: MemoryBankRepository) -> None:
        memory = a_memory(id="m1", content="A memory", source="bank1")
        bank = a_memory_bank(name="bank1", description="Has memories", memory_count=1, memories=[memory])
        assert repo.save(bank).is_ok

        result = repo.find_by_id("bank1")
        assert result.is_ok and result.value is not None
        assert result.value.memories == []
        assert result.value.memory_count == 1


# ---------------------------------------------------------------------------
# Upsert semantics
# ---------------------------------------------------------------------------


class TestUpsert:
    """Re-saving an existing name updates fields via ON CONFLICT(name) DO UPDATE."""

    def test_resave_existing_name_updates_fields_without_integrity_error(self, repo: MemoryBankRepository) -> None:
        assert repo.save(a_memory_bank(name="dup", description="v1", status="registered", memory_count=1)).is_ok
        # Re-saving the same name must NOT raise IntegrityError and must update.
        assert repo.save(
            a_memory_bank(
                name="dup",
                description="v2",
                status="suspended",
                created_at=_utc(2026, 1, 1),
                last_accessed=_utc(2026, 4, 4),
                memory_count=9,
            )
        ).is_ok

        result = repo.find_by_id("dup")
        assert result.is_ok and result.value is not None
        assert result.value.description == "v2"
        assert result.value.status == "suspended"
        assert result.value.memory_count == 9
        assert _row_count(repo._db_path) == 1


# ---------------------------------------------------------------------------
# memory_banks_db_path() helper + fresh bootstrap
# ---------------------------------------------------------------------------


class TestDbPathAndBootstrap:
    """memory_banks_db_path helper and repository init bootstrap."""

    def test_memory_banks_db_path_returns_expected_path(self, tmp_path: Path) -> None:
        assert memory_banks_db_path(tmp_path) == tmp_path / "memory_banks.db"

    def test_memory_banks_db_path_accepts_str(self, tmp_path: Path) -> None:
        assert memory_banks_db_path(str(tmp_path)) == tmp_path / "memory_banks.db"

    def test_init_creates_parent_dir_db_file_and_table(self, tmp_path: Path) -> None:
        db_path = tmp_path / "nested" / "deep" / "memory_banks.db"
        assert not db_path.parent.exists()

        repo = MemoryBankRepository(db_path)

        assert db_path.parent.is_dir()
        assert db_path.exists()
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'memory_banks'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None

    def test_bootstrap_is_idempotent(self, repo: MemoryBankRepository) -> None:
        # Re-initializing over the same db must not raise (create_all no-op).
        again = MemoryBankRepository(repo._db_path)
        assert again.list().is_ok


# ---------------------------------------------------------------------------
# WAL mode
# ---------------------------------------------------------------------------


class TestWalMode:
    """WAL mode is active on the created database."""

    def test_journal_mode_is_wal(self, repo: MemoryBankRepository) -> None:
        conn = sqlite3.connect(str(repo._db_path))
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        finally:
            conn.close()
        assert mode == "wal"
