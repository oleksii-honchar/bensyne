"""Unit tests for MemoryBank domain entity."""

from datetime import datetime

import pytest

from src.domain.entities.memory_bank import MemoryBank
from src.domain.result import ErrorWithDetails, Result


class TestMemoryBankOfValidData:
    """MemoryBank.of accepts valid data and returns Result.ok."""

    def test_of_returns_ok_with_valid_data(self):
        result = MemoryBank.of("my_bank", "A test bank")
        assert result.is_ok is True
        bank = result.value
        assert bank.name == "my_bank"
        assert bank.description == "A test bank"
        assert bank.status == "registered"
        assert bank.created_at is not None
        assert isinstance(bank.created_at, datetime)
        assert bank.last_accessed is None
        assert bank.memory_count == 0

    def test_of_returns_frozen_instance(self):
        result = MemoryBank.of("my_bank", "A test bank")
        assert result.is_ok is True
        bank = result.value
        with pytest.raises(Exception):
            bank.name = "mutated"  # type: ignore

    def test_of_sets_created_at_when_called(self):
        before = datetime.now()
        result = MemoryBank.of("my_bank", "A test bank")
        after = datetime.now()
        assert result.is_ok is True
        bank = result.value
        assert before <= bank.created_at <= after


class TestMemoryBankOfRejectsInvalidData:
    """MemoryBank.of rejects empty name/description and returns Result.ko."""

    def test_of_rejects_empty_name(self):
        result = MemoryBank.of("", "A test bank")
        assert result.is_ko is True
        assert result.value is None
        assert len(result.errors) > 0
        assert result.errors[0].error_code == "INVALID_MEMORY_BANK"

    def test_of_rejects_empty_description(self):
        result = MemoryBank.of("my_bank", "")
        assert result.is_ko is True
        assert result.value is None
        assert len(result.errors) > 0
        assert result.errors[0].error_code == "INVALID_MEMORY_BANK"

    def test_of_rejects_whitespace_only_name(self):
        result = MemoryBank.of("   ", "A test bank")
        assert result.is_ko is True
        assert result.value is None

    def test_of_rejects_whitespace_only_description(self):
        result = MemoryBank.of("my_bank", "   ")
        assert result.is_ko is True
        assert result.value is None

    def test_of_rejects_invalid_name_with_special_chars(self):
        result = MemoryBank.of("my-bank!", "A test bank")
        assert result.is_ko is True
        assert result.value is None

    def test_of_error_contains_name_in_details(self):
        result = MemoryBank.of("", "A test bank")
        assert result.is_ko is True
        assert result.errors[0].details.get("name") == ""


class TestMemoryBankActivate:
    """MemoryBank.activate transitions to active, rejects suspended."""

    def test_activate_registered_bank(self):
        bank = MemoryBank.of("my_bank", "A test bank").value
        before = datetime.now()
        result = bank.activate()
        after = datetime.now()
        assert result.is_ok is True
        activated = result.value
        assert activated.status == "active"
        assert activated.last_accessed is not None
        assert before <= activated.last_accessed <= after
        assert activated.name == bank.name
        assert activated.description == bank.description

    def test_activate_sets_last_accessed(self):
        bank = MemoryBank.of("my_bank", "A test bank").value
        result = bank.activate()
        assert result.is_ok is True
        assert result.value.last_accessed is not None

    def test_activate_rejects_suspended_bank(self):
        bank = MemoryBank.of("my_bank", "A test bank").value
        suspended = bank.suspend().value
        result = suspended.activate()
        assert result.is_ko is True
        assert result.value is None
        assert result.errors[0].error_code == "BANK_SUSPENDED"
        assert result.errors[0].details["name"] == "my_bank"

    def test_activate_active_bank_succeeds(self):
        bank = MemoryBank.of("my_bank", "A test bank").value
        activated = bank.activate().value
        result = activated.activate()
        assert result.is_ok is True
        assert result.value.status == "active"

    def test_activate_returns_new_instance(self):
        bank = MemoryBank.of("my_bank", "A test bank").value
        result = bank.activate()
        assert result.is_ok is True
        assert result.value is not bank


class TestMemoryBankSuspend:
    """MemoryBank.suspend transitions to suspended status."""

    def test_suspend_registered_bank(self):
        bank = MemoryBank.of("my_bank", "A test bank").value
        result = bank.suspend()
        assert result.is_ok is True
        suspended = result.value
        assert suspended.status == "suspended"
        assert suspended.name == bank.name
        assert suspended.description == bank.description

    def test_suspend_active_bank(self):
        bank = MemoryBank.of("my_bank", "A test bank").value
        activated = bank.activate().value
        result = activated.suspend()
        assert result.is_ok is True
        assert result.value.status == "suspended"

    def test_suspend_returns_new_instance(self):
        bank = MemoryBank.of("my_bank", "A test bank").value
        result = bank.suspend()
        assert result.is_ok is True
        assert result.value is not bank

    def test_suspend_preserves_other_fields(self):
        bank = MemoryBank.of("my_bank", "A test bank").value
        bank_with_count = bank.increment_memory_count().increment_memory_count()
        suspended = bank_with_count.suspend().value
        assert suspended.memory_count == 2
        assert suspended.name == "my_bank"
        assert suspended.description == "A test bank"


class TestMemoryBankIncrementDecrementCount:
    """MemoryBank increment/decrement maintain correct count with floor at 0."""

    def test_increment_memory_count(self):
        bank = MemoryBank.of("my_bank", "A test bank").value
        incremented = bank.increment_memory_count()
        assert incremented.memory_count == 1
        assert incremented is not bank

    def test_multiple_increments(self):
        bank = MemoryBank.of("my_bank", "A test bank").value
        result = bank.increment_memory_count().increment_memory_count().increment_memory_count()
        assert result.memory_count == 3

    def test_decrement_memory_count(self):
        bank = MemoryBank.of("my_bank", "A test bank").value
        with_count = bank.increment_memory_count().increment_memory_count()
        decremented = with_count.decrement_memory_count()
        assert decremented.memory_count == 1
        assert decremented is not with_count

    def test_decrement_floor_at_zero(self):
        bank = MemoryBank.of("my_bank", "A test bank").value
        assert bank.memory_count == 0
        decremented = bank.decrement_memory_count()
        assert decremented.memory_count == 0

    def test_decrement_below_zero_stays_at_zero(self):
        bank = MemoryBank.of("my_bank", "A test bank").value
        result = bank.decrement_memory_count().decrement_memory_count().decrement_memory_count()
        assert result.memory_count == 0

    def test_increment_then_decrement_roundtrip(self):
        bank = MemoryBank.of("my_bank", "A test bank").value
        result = bank.increment_memory_count().decrement_memory_count()
        assert result.memory_count == 0

    def test_increment_preserves_other_fields(self):
        bank = MemoryBank.of("my_bank", "A test bank").value
        incremented = bank.increment_memory_count()
        assert incremented.name == "my_bank"
        assert incremented.description == "A test bank"
        assert incremented.status == "registered"
        assert incremented.last_accessed is None

    def test_decrement_preserves_other_fields(self):
        bank = MemoryBank.of("my_bank", "A test bank").value
        with_count = bank.increment_memory_count()
        decremented = with_count.decrement_memory_count()
        assert decremented.name == "my_bank"
        assert decremented.status == "registered"


class TestMemoryBankReplace:
    """MemoryBank.replace creates new frozen instance with updated fields."""

    def test_replace_updates_single_field(self):
        bank = MemoryBank.of("my_bank", "A test bank").value
        updated = bank.replace(status="active")
        assert updated.status == "active"
        assert updated.name == bank.name
        assert updated.description == bank.description

    def test_replace_updates_multiple_fields(self):
        now = datetime.now()
        bank = MemoryBank.of("my_bank", "A test bank").value
        updated = bank.replace(status="active", last_accessed=now)
        assert updated.status == "active"
        assert updated.last_accessed == now
        assert updated.name == bank.name

    def test_replace_returns_new_instance(self):
        bank = MemoryBank.of("my_bank", "A test bank").value
        updated = bank.replace(status="active")
        assert updated is not bank

    def test_replace_preserves_unspecified_fields(self):
        bank = MemoryBank.of("my_bank", "A test bank").value
        with_count = bank.increment_memory_count()
        updated = with_count.replace(status="active")
        assert updated.memory_count == 1
        assert updated.created_at == with_count.created_at
