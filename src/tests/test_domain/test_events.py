"""Unit tests for domain events: MemoryRememberedEvent, MemoryForgottenEvent,
MemoryBankActivatedEvent, MemoryBankSuspendedEvent.

Each event:
- implements DomainEvent ABC (event_type, timestamp, get_name)
- has factory method of() returning Result
- validates non-empty inputs in factory
"""

from datetime import datetime

import pytest

from src.utils.result import DomainEvent, ErrorWithDetails, Result
from src.domain.events.memory_events import (
    MemoryRememberedEvent,
    MemoryForgottenEvent,
)
from src.domain.events.memory_bank_events import (
    MemoryBankActivatedEvent,
    MemoryBankSuspendedEvent,
)


class TestMemoryRememberedEvent:
    """MemoryRememberedEvent creation, validation, and serialization."""

    def test_factory_accepts_valid_inputs(self):
        result = MemoryRememberedEvent.of(bank_name="my_bank", memory_id="mem_1")
        assert result.is_ok is True
        event = result.value
        assert event.bank_name == "my_bank"
        assert event.memory_id == "mem_1"

    def test_factory_rejects_empty_bank_name(self):
        result = MemoryRememberedEvent.of(bank_name="", memory_id="mem_1")
        assert result.is_ko is True
        assert result.value is None
        assert len(result.errors) == 1
        assert result.errors[0].error_code == "INVALID_MEMORY_REMEMBERED_EVENT"

    def test_factory_rejects_empty_memory_id(self):
        result = MemoryRememberedEvent.of(bank_name="my_bank", memory_id="")
        assert result.is_ko is True
        assert result.value is None
        assert len(result.errors) == 1
        assert result.errors[0].error_code == "INVALID_MEMORY_REMEMBERED_EVENT"

    def test_factory_rejects_both_empty(self):
        result = MemoryRememberedEvent.of(bank_name="", memory_id="")
        assert result.is_ko is True
        assert result.value is None
        assert len(result.errors) == 1

    def test_event_type_is_memory_created(self):
        result = MemoryRememberedEvent.of(bank_name="b", memory_id="m")
        event = result.value
        assert event.event_type == "memory.remembered"

    def test_get_name_returns_memory_created(self):
        result = MemoryRememberedEvent.of(bank_name="b", memory_id="m")
        event = result.value
        assert event.get_name() == "memory.remembered"

    def test_timestamp_is_datetime(self):
        result = MemoryRememberedEvent.of(bank_name="b", memory_id="m")
        event = result.value
        assert isinstance(event.timestamp, datetime)

    def test_is_domain_event(self):
        result = MemoryRememberedEvent.of(bank_name="b", memory_id="m")
        event = result.value
        assert isinstance(event, DomainEvent)


class TestMemoryForgottenEvent:
    """MemoryForgottenEvent creation, validation, and serialization."""

    def test_factory_accepts_valid_inputs(self):
        result = MemoryForgottenEvent.of(bank_name="my_bank", memory_id="mem_2")
        assert result.is_ok is True
        event = result.value
        assert event.bank_name == "my_bank"
        assert event.memory_id == "mem_2"

    def test_factory_rejects_empty_bank_name(self):
        result = MemoryForgottenEvent.of(bank_name="", memory_id="mem_2")
        assert result.is_ko is True
        assert result.value is None
        assert len(result.errors) == 1
        assert result.errors[0].error_code == "INVALID_MEMORY_FORGOTTEN_EVENT"

    def test_factory_rejects_empty_memory_id(self):
        result = MemoryForgottenEvent.of(bank_name="my_bank", memory_id="")
        assert result.is_ko is True
        assert result.value is None
        assert len(result.errors) == 1
        assert result.errors[0].error_code == "INVALID_MEMORY_FORGOTTEN_EVENT"

    def test_event_type_is_memory_deleted(self):
        result = MemoryForgottenEvent.of(bank_name="b", memory_id="m")
        event = result.value
        assert event.event_type == "memory.forgotten"

    def test_get_name_returns_memory_deleted(self):
        result = MemoryForgottenEvent.of(bank_name="b", memory_id="m")
        event = result.value
        assert event.get_name() == "memory.forgotten"

    def test_timestamp_is_datetime(self):
        result = MemoryForgottenEvent.of(bank_name="b", memory_id="m")
        event = result.value
        assert isinstance(event.timestamp, datetime)

    def test_is_domain_event(self):
        result = MemoryForgottenEvent.of(bank_name="b", memory_id="m")
        event = result.value
        assert isinstance(event, DomainEvent)


class TestMemoryBankActivatedEvent:
    """MemoryBankActivatedEvent creation, validation, and serialization."""

    def test_factory_accepts_valid_inputs(self):
        result = MemoryBankActivatedEvent.of(bank_name="my_bank")
        assert result.is_ok is True
        event = result.value
        assert event.bank_name == "my_bank"

    def test_factory_rejects_empty_bank_name(self):
        result = MemoryBankActivatedEvent.of(bank_name="")
        assert result.is_ko is True
        assert result.value is None
        assert len(result.errors) == 1
        assert result.errors[0].error_code == "INVALID_MEMORY_BANK_ACTIVATED_EVENT"

    def test_event_type_is_memory_bank_activated(self):
        result = MemoryBankActivatedEvent.of(bank_name="b")
        event = result.value
        assert event.event_type == "memory_bank.activated"

    def test_get_name_returns_memory_bank_activated(self):
        result = MemoryBankActivatedEvent.of(bank_name="b")
        event = result.value
        assert event.get_name() == "memory_bank.activated"

    def test_timestamp_is_datetime(self):
        result = MemoryBankActivatedEvent.of(bank_name="b")
        event = result.value
        assert isinstance(event.timestamp, datetime)

    def test_is_domain_event(self):
        result = MemoryBankActivatedEvent.of(bank_name="b")
        event = result.value
        assert isinstance(event, DomainEvent)


class TestMemoryBankSuspendedEvent:
    """MemoryBankSuspendedEvent creation, validation, and serialization."""

    def test_factory_accepts_valid_inputs(self):
        result = MemoryBankSuspendedEvent.of(bank_name="my_bank")
        assert result.is_ok is True
        event = result.value
        assert event.bank_name == "my_bank"

    def test_factory_rejects_empty_bank_name(self):
        result = MemoryBankSuspendedEvent.of(bank_name="")
        assert result.is_ko is True
        assert result.value is None
        assert len(result.errors) == 1
        assert result.errors[0].error_code == "INVALID_MEMORY_BANK_SUSPENDED_EVENT"

    def test_event_type_is_memory_bank_suspended(self):
        result = MemoryBankSuspendedEvent.of(bank_name="b")
        event = result.value
        assert event.event_type == "memory_bank.suspended"

    def test_get_name_returns_memory_bank_suspended(self):
        result = MemoryBankSuspendedEvent.of(bank_name="b")
        event = result.value
        assert event.get_name() == "memory_bank.suspended"

    def test_timestamp_is_datetime(self):
        result = MemoryBankSuspendedEvent.of(bank_name="b")
        event = result.value
        assert isinstance(event.timestamp, datetime)

    def test_is_domain_event(self):
        result = MemoryBankSuspendedEvent.of(bank_name="b")
        event = result.value
        assert isinstance(event, DomainEvent)


class TestEventTypesCorrect:
    """Verify all event_type values match spec."""

    def test_memory_created_event_type(self):
        event = MemoryRememberedEvent.of("b", "m").value
        assert event.event_type == "memory.remembered"

    def test_memory_deleted_event_type(self):
        event = MemoryForgottenEvent.of("b", "m").value
        assert event.event_type == "memory.forgotten"

    def test_memory_bank_activated_event_type(self):
        event = MemoryBankActivatedEvent.of("b").value
        assert event.event_type == "memory_bank.activated"

    def test_memory_bank_suspended_event_type(self):
        event = MemoryBankSuspendedEvent.of("b").value
        assert event.event_type == "memory_bank.suspended"
