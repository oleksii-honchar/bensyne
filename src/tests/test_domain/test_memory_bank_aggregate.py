"""Unit tests for MemoryBankAggregate."""

from datetime import datetime

from typing import Optional

import pytest

from src.domain.aggregates.memory_bank_aggregate import MemoryBankAggregate
from src.domain.entities.memory import Memory
from src.domain.entities.memory_bank import MemoryBank
from src.domain.events.memory_events import (
    MemoryBankActivatedEvent,
    MemoryBankSuspendedEvent,
    MemoryCreatedEvent,
    MemoryDeletedEvent,
)
from src.domain.result import Result


def _make_active_bank(name: str = "test_bank", description: str = "A test bank") -> MemoryBank:
    """Create an active MemoryBank for tests."""
    bank = MemoryBank.of(name, description).value
    return bank.activate().value


def _make_memory(
    id: str = "mem1",
    content: str = "Test content",
    importance: float = 0.5,
    source: str = "conversation",
    scope: str = "working",
    created_at: Optional[datetime] = None,
) -> Memory:
    """Create a Memory for tests."""
    return Memory.of({
        "id": id,
        "content": content,
        "importance": importance,
        "source": source,
        "scope": scope,
        "created_at": created_at or datetime.now(),
    }).value


class TestMemoryBankAggregateOf:
    """MemoryBankAggregate.of returns Result[MemoryBankAggregate]."""

    def test_of_returns_ok_with_bank_and_memories(self):
        bank = _make_active_bank()
        memory = _make_memory()
        result = MemoryBankAggregate.of(bank, [memory])
        assert result.is_ok is True
        agg = result.value
        assert agg.bank is bank
        assert agg.memories == [memory]

    def test_of_returns_ok_with_empty_memories(self):
        bank = _make_active_bank()
        result = MemoryBankAggregate.of(bank)
        assert result.is_ok is True
        agg = result.value
        assert agg.bank is bank
        assert agg.memories == []

    def test_of_returns_frozen_instance(self):
        bank = _make_active_bank()
        agg = MemoryBankAggregate.of(bank).value
        with pytest.raises(Exception):
            agg.bank = None  # type: ignore

    def test_of_with_none_memories_defaults_to_empty_list(self):
        bank = _make_active_bank()
        result = MemoryBankAggregate.of(bank, None)
        assert result.is_ok is True
        assert result.value.memories == []


class TestRememberRejectsInactiveBank:
    """remember() rejects when bank is not active with Result.ko."""

    def test_remember_rejects_registered_bank(self):
        bank = MemoryBank.of("test_bank", "A test bank").value
        agg = MemoryBankAggregate.of(bank).value
        memory = _make_memory()
        result = agg.remember(memory)
        assert result.is_ko is True
        assert result.value is None
        assert result.errors[0].error_code == "BANK_NOT_ACTIVE"
        assert result.errors[0].details["name"] == "test_bank"

    def test_remember_rejects_suspended_bank(self):
        bank = _make_active_bank().suspend().value
        agg = MemoryBankAggregate.of(bank).value
        memory = _make_memory()
        result = agg.remember(memory)
        assert result.is_ko is True
        assert result.errors[0].error_code == "BANK_NOT_ACTIVE"

    def test_remember_rejects_preserves_aggregate(self):
        bank = MemoryBank.of("test_bank", "A test bank").value
        agg = MemoryBankAggregate.of(bank).value
        memory = _make_memory()
        result = agg.remember(memory)
        assert result.is_ko is True
        assert agg.memories == []


class TestRememberProducesEvent:
    """remember() produces MemoryCreatedEvent in Result.events on success."""

    def test_remember_produces_memory_created_event(self):
        bank = _make_active_bank()
        agg = MemoryBankAggregate.of(bank).value
        memory = _make_memory("mem1")
        result = agg.remember(memory)
        assert result.is_ok is True
        assert len(result.events) == 1
        event = result.events[0]
        assert isinstance(event, MemoryCreatedEvent)
        assert event.bank_name == "test_bank"
        assert event.memory_id == "mem1"

    def test_remember_adds_memory_to_list(self):
        bank = _make_active_bank()
        agg = MemoryBankAggregate.of(bank).value
        memory = _make_memory("mem1")
        result = agg.remember(memory)
        assert result.is_ok is True
        new_agg = result.value
        assert len(new_agg.memories) == 1
        assert new_agg.memories[0].id == "mem1"

    def test_remember_increments_memory_count(self):
        bank = _make_active_bank()
        agg = MemoryBankAggregate.of(bank).value
        memory = _make_memory("mem1")
        result = agg.remember(memory)
        assert result.is_ok is True
        new_agg = result.value
        assert new_agg.bank.memory_count == 1

    def test_remember_returns_new_aggregate(self):
        bank = _make_active_bank()
        agg = MemoryBankAggregate.of(bank).value
        memory = _make_memory("mem1")
        result = agg.remember(memory)
        assert result.is_ok is True
        assert result.value is not agg

    def test_remember_preserves_existing_memories(self):
        bank = _make_active_bank()
        existing = _make_memory("existing")
        agg = MemoryBankAggregate.of(bank, [existing]).value
        new_memory = _make_memory("new")
        result = agg.remember(new_memory)
        assert result.is_ok is True
        new_agg = result.value
        assert len(new_agg.memories) == 2
        assert new_agg.memories[0].id == "existing"
        assert new_agg.memories[1].id == "new"

    def test_remember_events_not_stored_on_aggregate(self):
        bank = _make_active_bank()
        agg = MemoryBankAggregate.of(bank).value
        memory = _make_memory("mem1")
        result = agg.remember(memory)
        assert result.is_ok is True
        # Events are in Result.events, not on the aggregate
        assert not hasattr(result.value, "events")


class TestForgetRejectsNotFound:
    """forget() rejects when memory_id is not found."""

    def test_forget_rejects_nonexistent_memory(self):
        bank = _make_active_bank()
        agg = MemoryBankAggregate.of(bank).value
        result = agg.forget("nonexistent")
        assert result.is_ko is True
        assert result.value is None
        assert result.errors[0].error_code == "MEMORY_NOT_FOUND"
        assert result.errors[0].details["id"] == "nonexistent"

    def test_forget_rejects_on_empty_aggregate(self):
        bank = _make_active_bank()
        agg = MemoryBankAggregate.of(bank).value
        result = agg.forget("any_id")
        assert result.is_ko is True
        assert result.errors[0].error_code == "MEMORY_NOT_FOUND"


class TestForgetProducesEvent:
    """forget() produces MemoryDeletedEvent when successful."""

    def test_forget_produces_memory_deleted_event(self):
        bank = _make_active_bank()
        memory = _make_memory("mem1")
        agg = MemoryBankAggregate.of(bank, [memory]).value
        result = agg.forget("mem1")
        assert result.is_ok is True
        assert len(result.events) == 1
        event = result.events[0]
        assert isinstance(event, MemoryDeletedEvent)
        assert event.bank_name == "test_bank"
        assert event.memory_id == "mem1"

    def test_forget_removes_memory_from_list(self):
        bank = _make_active_bank()
        mem1 = _make_memory("mem1")
        mem2 = _make_memory("mem2")
        agg = MemoryBankAggregate.of(bank, [mem1, mem2]).value
        result = agg.forget("mem1")
        assert result.is_ok is True
        new_agg = result.value
        assert len(new_agg.memories) == 1
        assert new_agg.memories[0].id == "mem2"

    def test_forget_decrements_memory_count(self):
        bank = _make_active_bank()
        bank_with_count = bank.increment_memory_count()
        memory = _make_memory("mem1")
        agg = MemoryBankAggregate.of(bank_with_count, [memory]).value
        result = agg.forget("mem1")
        assert result.is_ok is True
        new_agg = result.value
        assert new_agg.bank.memory_count == 0

    def test_forget_returns_new_aggregate(self):
        bank = _make_active_bank()
        memory = _make_memory("mem1")
        agg = MemoryBankAggregate.of(bank, [memory]).value
        result = agg.forget("mem1")
        assert result.is_ok is True
        assert result.value is not agg

    def test_forget_events_not_stored_on_aggregate(self):
        bank = _make_active_bank()
        memory = _make_memory("mem1")
        agg = MemoryBankAggregate.of(bank, [memory]).value
        result = agg.forget("mem1")
        assert result.is_ok is True
        assert not hasattr(result.value, "events")


class TestActivate:
    """activate() activates bank, produces MemoryBankActivatedEvent."""

    def test_activate_produces_event(self):
        bank = MemoryBank.of("test_bank", "A test bank").value
        agg = MemoryBankAggregate.of(bank).value
        result = agg.activate()
        assert result.is_ok is True
        assert len(result.events) == 1
        event = result.events[0]
        assert isinstance(event, MemoryBankActivatedEvent)
        assert event.bank_name == "test_bank"

    def test_activate_changes_bank_status(self):
        bank = MemoryBank.of("test_bank", "A test bank").value
        agg = MemoryBankAggregate.of(bank).value
        result = agg.activate()
        assert result.is_ok is True
        new_agg = result.value
        assert new_agg.bank.status == "active"

    def test_activate_preserves_memories(self):
        bank = MemoryBank.of("test_bank", "A test bank").value
        memory = _make_memory("mem1")
        agg = MemoryBankAggregate.of(bank, [memory]).value
        result = agg.activate()
        assert result.is_ok is True
        new_agg = result.value
        assert len(new_agg.memories) == 1
        assert new_agg.memories[0].id == "mem1"

    def test_activate_returns_new_aggregate(self):
        bank = MemoryBank.of("test_bank", "A test bank").value
        agg = MemoryBankAggregate.of(bank).value
        result = agg.activate()
        assert result.is_ok is True
        assert result.value is not agg

    def test_activate_rejects_suspended_bank(self):
        bank = MemoryBank.of("test_bank", "A test bank").value
        suspended = bank.suspend().value
        agg = MemoryBankAggregate.of(suspended).value
        result = agg.activate()
        assert result.is_ko is True
        assert result.errors[0].error_code == "BANK_SUSPENDED"

    def test_activate_events_not_stored_on_aggregate(self):
        bank = MemoryBank.of("test_bank", "A test bank").value
        agg = MemoryBankAggregate.of(bank).value
        result = agg.activate()
        assert result.is_ok is True
        assert not hasattr(result.value, "events")


class TestSuspend:
    """suspend() suspends bank, produces MemoryBankSuspendedEvent."""

    def test_suspend_produces_event(self):
        bank = _make_active_bank()
        agg = MemoryBankAggregate.of(bank).value
        result = agg.suspend()
        assert result.is_ok is True
        assert len(result.events) == 1
        event = result.events[0]
        assert isinstance(event, MemoryBankSuspendedEvent)
        assert event.bank_name == "test_bank"

    def test_suspend_changes_bank_status(self):
        bank = _make_active_bank()
        agg = MemoryBankAggregate.of(bank).value
        result = agg.suspend()
        assert result.is_ok is True
        new_agg = result.value
        assert new_agg.bank.status == "suspended"

    def test_suspend_preserves_memories(self):
        bank = _make_active_bank()
        memory = _make_memory("mem1")
        agg = MemoryBankAggregate.of(bank, [memory]).value
        result = agg.suspend()
        assert result.is_ok is True
        new_agg = result.value
        assert len(new_agg.memories) == 1
        assert new_agg.memories[0].id == "mem1"

    def test_suspend_returns_new_aggregate(self):
        bank = _make_active_bank()
        agg = MemoryBankAggregate.of(bank).value
        result = agg.suspend()
        assert result.is_ok is True
        assert result.value is not agg

    def test_suspend_events_not_stored_on_aggregate(self):
        bank = _make_active_bank()
        agg = MemoryBankAggregate.of(bank).value
        result = agg.suspend()
        assert result.is_ok is True
        assert not hasattr(result.value, "events")
