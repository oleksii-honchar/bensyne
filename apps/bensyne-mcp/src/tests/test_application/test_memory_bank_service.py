"""Unit + integration-style tests for MemoryBankService (application layer).

MemoryBankService is the SOLE business API for bank operations (U7/U14):
pure orchestration over MemoryBankRepository + the MemoryBank aggregate.
Unit tests use the InMemoryMemoryBankRepository fake (domain_test_utils);
the integration-style test exercises a REAL MemoryBankRepository against a
tmp db across two service instances (persistence across restarts, S6).
"""

from __future__ import annotations

import pytest

from src.application.services.memory_bank_service import MemoryBankService
from src.domain.memory_bank_aggregate import MemoryBank
from src.infrastructure.bank.memory_bank_repository import (
    MemoryBankRepository,
    memory_banks_db_path,
)
from src.tests.test_domain.domain_test_utils import (
    InMemoryMemoryBankRepository,
    a_memory_bank_repository,
)
from src.utils.result import Result
from src.utils.structured_logging import LoggerMock


def _a_service(
    repository: InMemoryMemoryBankRepository | None = None,
) -> tuple[MemoryBankService, InMemoryMemoryBankRepository]:
    """Build a service over a fresh fake repo, returning (service, repo)."""
    repo = repository or a_memory_bank_repository()
    service = MemoryBankService(memory_bank_repository=repo, logger=LoggerMock())
    return service, repo


# ---------------------------------------------------------------------------
# register_memory_bank
# ---------------------------------------------------------------------------


def test_register_absent_bank_creates_with_registered_status_and_persists() -> None:
    service, repo = _a_service()

    result = service.register_memory_bank("alpha", "Alpha bank")

    assert result.is_ok
    bank = result.value
    assert bank is not None
    assert bank.name == "alpha"
    assert bank.status == "registered"
    assert bank.description == "Alpha bank"
    # Persisted: the repository now holds the row.
    stored = repo.find_by_id("alpha")
    assert stored.is_ok
    assert stored.value is not None
    assert stored.value.name == "alpha"
    assert stored.value.status == "registered"
    assert stored.value.description == "Alpha bank"
    assert len(repo.list().value or []) == 1


def test_register_existing_bank_updates_description_preserving_identity() -> None:
    service, repo = _a_service()
    service.register_memory_bank("alpha", "Original description")

    result = service.register_memory_bank("alpha", "Updated description")

    assert result.is_ok
    bank = result.value
    assert bank is not None
    # Old description replaced.
    assert bank.description == "Updated description"
    # Identity fields preserved.
    assert bank.name == "alpha"
    assert bank.status == "registered"
    assert bank.memory_count == 0
    # Single row — the update path upserted, never duplicated.
    listed = repo.list()
    assert listed.is_ok
    assert listed.value is not None
    assert len(listed.value) == 1
    stored = repo.find_by_id("alpha")
    assert stored.is_ok
    assert stored.value is not None
    assert stored.value.description == "Updated description"


def test_register_empty_description_rejected_without_write() -> None:
    service, repo = _a_service()

    result = service.register_memory_bank("alpha", "   ")

    assert result.is_ko
    assert result.errors[0].error_code == "INVALID_MEMORY_BANK"
    # Domain invariant — no repository write happened.
    stored = repo.find_by_id("alpha")
    assert stored.is_ok
    assert stored.value is None
    assert len(repo.list().value or []) == 0


def test_register_existing_bank_with_whitespace_description_keeps_old_value() -> None:
    service, repo = _a_service()
    service.register_memory_bank("alpha", "Original description")

    result = service.register_memory_bank("alpha", " \t ")

    assert result.is_ko
    assert result.errors[0].error_code == "INVALID_MEMORY_BANK"
    stored = repo.find_by_id("alpha")
    assert stored.is_ok
    assert stored.value is not None
    assert stored.value.description == "Original description"
    assert len(repo.list().value or []) == 1


# ---------------------------------------------------------------------------
# get_memory_bank / list_memory_banks
# ---------------------------------------------------------------------------


def test_get_memory_bank_returns_bank_for_existing() -> None:
    service, repo = _a_service()
    service.register_memory_bank("alpha", "Alpha bank")

    result = service.get_memory_bank("alpha")

    assert result.is_ok
    assert result.value is not None
    assert result.value.name == "alpha"
    assert result.value.description == "Alpha bank"


def test_get_memory_bank_returns_none_for_absent() -> None:
    service, _ = _a_service()

    result = service.get_memory_bank("missing")

    assert result.is_ok
    assert result.value is None


def test_list_memory_banks_returns_all() -> None:
    service, _ = _a_service()
    service.register_memory_bank("alpha", "Alpha bank")
    service.register_memory_bank("beta", "Beta bank")

    result = service.list_memory_banks()

    assert result.is_ok
    names = {bank.name for bank in (result.value or [])}
    assert names == {"alpha", "beta"}
    assert {bank.description for bank in (result.value or [])} == {
        "Alpha bank",
        "Beta bank",
    }


# ---------------------------------------------------------------------------
# ensure_default_bank (idempotent seed)
# ---------------------------------------------------------------------------


def test_ensure_default_bank_seeds_when_absent() -> None:
    service, repo = _a_service()

    service.ensure_default_bank("Default bank")

    stored = repo.find_by_id("default")
    assert stored.is_ok
    assert stored.value is not None
    assert stored.value.name == "default"
    assert stored.value.description == "Default bank"
    assert stored.value.status == "registered"
    assert len(repo.list().value or []) == 1


def test_ensure_default_bank_never_overwrites_existing_description() -> None:
    service, repo = _a_service()

    service.ensure_default_bank("First description")
    service.ensure_default_bank("A different description")

    stored = repo.find_by_id("default")
    assert stored.is_ok
    assert stored.value is not None
    # Idempotent: the FIRST description is retained, never overwritten.
    assert stored.value.description == "First description"
    assert len(repo.list().value or []) == 1


# ---------------------------------------------------------------------------
# Integration-style: real MemoryBankRepository, persistence across restarts
# ---------------------------------------------------------------------------


def test_round_trip_across_service_instances_with_real_repository(tmp_path) -> None:
    db_path = memory_banks_db_path(tmp_path)

    # First "boot": seed default + register a bank.
    repo1 = MemoryBankRepository(db_path=db_path)
    service1 = MemoryBankService(memory_bank_repository=repo1, logger=LoggerMock())
    service1.ensure_default_bank("Default personal memory")
    register_result = service1.register_memory_bank("persisted", "Persisted bank")
    assert register_result.is_ok

    # Second "boot": a fresh repository + service over the SAME db file.
    repo2 = MemoryBankRepository(db_path=db_path)
    service2 = MemoryBankService(memory_bank_repository=repo2, logger=LoggerMock())

    default = service2.get_memory_bank("default")
    assert default.is_ok
    assert default.value is not None
    assert default.value.description == "Default personal memory"
    assert default.value.status == "registered"

    persisted = service2.get_memory_bank("persisted")
    assert persisted.is_ok
    assert persisted.value is not None
    assert persisted.value.description == "Persisted bank"
    assert persisted.value.name == "persisted"

    listed = service2.list_memory_banks()
    assert listed.is_ok
    assert {bank.name for bank in (listed.value or [])} == {"default", "persisted"}

    # Idempotency survives restart: a different seed description is ignored.
    service2.ensure_default_bank("Should not overwrite")
    after = service2.get_memory_bank("default")
    assert after.is_ok
    assert after.value is not None
    assert after.value.description == "Default personal memory"
