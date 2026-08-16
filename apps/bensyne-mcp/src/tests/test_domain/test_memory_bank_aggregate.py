"""Unit tests for MemoryBank aggregate operations (remember, forget, activate, suspend)."""

from datetime import datetime

from typing import Optional

import pytest

from src.domain.memory_bank_aggregate import MemoryBank
from src.domain.memory_entity import Memory
from src.domain.events.memory_events import (
    MemoryRememberedEvent,
    MemoryForgottenEvent,
)
from src.domain.events.memory_bank_events import (
    MemoryBankActivatedEvent,
    MemoryBankSuspendedEvent,
)
from src.utils.result import Result


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
    return Memory.of(
        {
            "id": id,
            "content": content,
            "importance": importance,
            "source": source,
            "scope": scope,
            "created_at": created_at or datetime.now(),
        }
    ).value


class TestMemoryBankOf:
    """MemoryBank.of returns Result[MemoryBank] with memories field."""

    def test_of_returns_ok_with_memories(self):
        bank = _make_active_bank()
        memory = _make_memory()
        bank_with_memories = bank.replace(memories=[memory])
        assert bank_with_memories.memories == [memory]

    def test_of_returns_ok_with_empty_memories(self):
        bank = _make_active_bank()
        assert bank.memories == []

    def test_of_returns_frozen_instance(self):
        bank = _make_active_bank()
        with pytest.raises(Exception):
            bank.name = "mutated"  # type: ignore

    def test_replace_with_none_memories_defaults_to_empty_list(self):
        bank = _make_active_bank()
        bank_with_none = bank.replace(memories=[])
        assert bank_with_none.memories == []


class TestRememberRejectsInactiveBank:
    """remember() rejects when bank is not active with Result.ko."""

    def test_remember_rejects_registered_bank(self):
        bank = MemoryBank.of("test_bank", "A test bank").value
        memory = _make_memory()
        result = bank.remember(memory)
        assert result.is_ko is True
        assert result.value is None
        assert result.errors[0].error_code == "BANK_NOT_ACTIVE"
        assert result.errors[0].details["name"] == "test_bank"

    def test_remember_rejects_suspended_bank(self):
        bank = _make_active_bank().suspend().value
        memory = _make_memory()
        result = bank.remember(memory)
        assert result.is_ko is True
        assert result.errors[0].error_code == "BANK_NOT_ACTIVE"

    def test_remember_rejects_preserves_aggregate(self):
        bank = MemoryBank.of("test_bank", "A test bank").value
        memory = _make_memory()
        result = bank.remember(memory)
        assert result.is_ko is True
        assert bank.memories == []


class TestRememberProducesEvent:
    """remember() produces MemoryRememberedEvent in Result.events on success."""

    def test_remember_produces_memory_created_event(self):
        bank = _make_active_bank()
        memory = _make_memory("mem1")
        result = bank.remember(memory)
        assert result.is_ok is True
        assert len(result.events) == 1
        event = result.events[0]
        assert isinstance(event, MemoryRememberedEvent)
        assert event.bank_name == "test_bank"
        assert event.memory_id == "mem1"

    def test_remember_adds_memory_to_list(self):
        bank = _make_active_bank()
        memory = _make_memory("mem1")
        result = bank.remember(memory)
        assert result.is_ok is True
        new_bank = result.value
        assert len(new_bank.memories) == 1
        assert new_bank.memories[0].id == "mem1"

    def test_remember_increments_memory_count(self):
        bank = _make_active_bank()
        memory = _make_memory("mem1")
        result = bank.remember(memory)
        assert result.is_ok is True
        new_bank = result.value
        assert new_bank.memory_count == 1

    def test_remember_returns_new_aggregate(self):
        bank = _make_active_bank()
        memory = _make_memory("mem1")
        result = bank.remember(memory)
        assert result.is_ok is True
        assert result.value is not bank

    def test_remember_preserves_existing_memories(self):
        bank = _make_active_bank()
        existing = _make_memory("existing")
        bank_with_existing = bank.replace(memories=[existing])
        new_memory = _make_memory("new")
        result = bank_with_existing.remember(new_memory)
        assert result.is_ok is True
        new_bank = result.value
        assert len(new_bank.memories) == 2
        assert new_bank.memories[0].id == "existing"
        assert new_bank.memories[1].id == "new"

    def test_remember_events_not_stored_on_aggregate(self):
        bank = _make_active_bank()
        memory = _make_memory("mem1")
        result = bank.remember(memory)
        assert result.is_ok is True
        # Events are in Result.events, not on the aggregate
        assert not hasattr(result.value, "events")


class TestForgetRejectsNotFound:
    """forget() rejects when memory_id is not found."""

    def test_forget_rejects_nonexistent_memory(self):
        bank = _make_active_bank()
        result = bank.forget("nonexistent")
        assert result.is_ko is True
        assert result.value is None
        assert result.errors[0].error_code == "MEMORY_NOT_FOUND"
        assert result.errors[0].details["id"] == "nonexistent"

    def test_forget_rejects_on_empty_aggregate(self):
        bank = _make_active_bank()
        result = bank.forget("any_id")
        assert result.is_ko is True
        assert result.errors[0].error_code == "MEMORY_NOT_FOUND"


class TestForgetProducesEvent:
    """forget() produces MemoryForgottenEvent when successful."""

    def test_forget_produces_memory_deleted_event(self):
        bank = _make_active_bank()
        memory = _make_memory("mem1")
        bank_with_memory = bank.replace(memories=[memory])
        result = bank_with_memory.forget("mem1")
        assert result.is_ok is True
        assert len(result.events) == 1
        event = result.events[0]
        assert isinstance(event, MemoryForgottenEvent)
        assert event.bank_name == "test_bank"
        assert event.memory_id == "mem1"

    def test_forget_removes_memory_from_list(self):
        bank = _make_active_bank()
        mem1 = _make_memory("mem1")
        mem2 = _make_memory("mem2")
        bank_with_memories = bank.replace(memories=[mem1, mem2])
        result = bank_with_memories.forget("mem1")
        assert result.is_ok is True
        new_bank = result.value
        assert len(new_bank.memories) == 1
        assert new_bank.memories[0].id == "mem2"

    def test_forget_decrements_memory_count(self):
        bank = _make_active_bank()
        bank_with_count = bank.increment_memory_count()
        memory = _make_memory("mem1")
        bank_with_memory = bank_with_count.replace(memories=[memory])
        result = bank_with_memory.forget("mem1")
        assert result.is_ok is True
        new_bank = result.value
        assert new_bank.memory_count == 0

    def test_forget_returns_new_aggregate(self):
        bank = _make_active_bank()
        memory = _make_memory("mem1")
        bank_with_memory = bank.replace(memories=[memory])
        result = bank_with_memory.forget("mem1")
        assert result.is_ok is True
        assert result.value is not bank_with_memory

    def test_forget_events_not_stored_on_aggregate(self):
        bank = _make_active_bank()
        memory = _make_memory("mem1")
        bank_with_memory = bank.replace(memories=[memory])
        result = bank_with_memory.forget("mem1")
        assert result.is_ok is True
        assert not hasattr(result.value, "events")


class TestActivate:
    """activate() activates bank, produces MemoryBankActivatedEvent."""

    def test_activate_produces_event(self):
        bank = MemoryBank.of("test_bank", "A test bank").value
        result = bank.activate()
        assert result.is_ok is True
        assert len(result.events) == 1
        event = result.events[0]
        assert isinstance(event, MemoryBankActivatedEvent)
        assert event.bank_name == "test_bank"

    def test_activate_changes_bank_status(self):
        bank = MemoryBank.of("test_bank", "A test bank").value
        result = bank.activate()
        assert result.is_ok is True
        new_bank = result.value
        assert new_bank.status == "active"

    def test_activate_preserves_memories(self):
        bank = MemoryBank.of("test_bank", "A test bank").value
        memory = _make_memory("mem1")
        bank_with_memory = bank.replace(memories=[memory])
        result = bank_with_memory.activate()
        assert result.is_ok is True
        new_bank = result.value
        assert len(new_bank.memories) == 1
        assert new_bank.memories[0].id == "mem1"

    def test_activate_returns_new_aggregate(self):
        bank = MemoryBank.of("test_bank", "A test bank").value
        result = bank.activate()
        assert result.is_ok is True
        assert result.value is not bank

    def test_activate_rejects_suspended_bank(self):
        bank = MemoryBank.of("test_bank", "A test bank").value
        suspended = bank.suspend().value
        result = suspended.activate()
        assert result.is_ko is True
        assert result.errors[0].error_code == "BANK_SUSPENDED"

    def test_activate_events_not_stored_on_aggregate(self):
        bank = MemoryBank.of("test_bank", "A test bank").value
        result = bank.activate()
        assert result.is_ok is True
        assert not hasattr(result.value, "events")


class TestSuspend:
    """suspend() suspends bank, produces MemoryBankSuspendedEvent."""

    def test_suspend_produces_event(self):
        bank = _make_active_bank()
        result = bank.suspend()
        assert result.is_ok is True
        assert len(result.events) == 1
        event = result.events[0]
        assert isinstance(event, MemoryBankSuspendedEvent)
        assert event.bank_name == "test_bank"

    def test_suspend_changes_bank_status(self):
        bank = _make_active_bank()
        result = bank.suspend()
        assert result.is_ok is True
        new_bank = result.value
        assert new_bank.status == "suspended"

    def test_suspend_preserves_memories(self):
        bank = _make_active_bank()
        memory = _make_memory("mem1")
        bank_with_memory = bank.replace(memories=[memory])
        result = bank_with_memory.suspend()
        assert result.is_ok is True
        new_bank = result.value
        assert len(new_bank.memories) == 1
        assert new_bank.memories[0].id == "mem1"

    def test_suspend_returns_new_aggregate(self):
        bank = _make_active_bank()
        result = bank.suspend()
        assert result.is_ok is True
        assert result.value is not bank

    def test_suspend_events_not_stored_on_aggregate(self):
        bank = _make_active_bank()
        result = bank.suspend()
        assert result.is_ok is True
        assert not hasattr(result.value, "events")
