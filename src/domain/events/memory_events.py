"""Concrete domain events for memory and memory bank operations.

Each event implements DomainEvent ABC and has a factory method of() that
returns Result, validating non-empty inputs.
"""

from dataclasses import dataclass
from datetime import datetime

from src.domain.result import DomainEvent, ErrorWithDetails, Result


@dataclass(frozen=True)
class MemoryCreatedEvent(DomainEvent):
    """Emitted when a new memory is created in a memory bank."""

    bank_name: str
    memory_id: str
    timestamp: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now())

    @classmethod
    def of(cls, bank_name: str, memory_id: str) -> Result["MemoryCreatedEvent"]:
        if not bank_name or not memory_id:
            return Result.ko([ErrorWithDetails("INVALID_MEMORY_CREATED_EVENT", {
                "bank_name": bank_name,
                "memory_id": memory_id,
            })])
        return Result.ok(cls(bank_name=bank_name, memory_id=memory_id))

    @property
    def event_type(self) -> str:
        return "memory.created"

    def get_name(self) -> str:
        return "memory.created"


@dataclass(frozen=True)
class MemoryDeletedEvent(DomainEvent):
    """Emitted when a memory is deleted from a memory bank."""

    bank_name: str
    memory_id: str
    timestamp: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now())

    @classmethod
    def of(cls, bank_name: str, memory_id: str) -> Result["MemoryDeletedEvent"]:
        if not bank_name or not memory_id:
            return Result.ko([ErrorWithDetails("INVALID_MEMORY_DELETED_EVENT", {
                "bank_name": bank_name,
                "memory_id": memory_id,
            })])
        return Result.ok(cls(bank_name=bank_name, memory_id=memory_id))

    @property
    def event_type(self) -> str:
        return "memory.deleted"

    def get_name(self) -> str:
        return "memory.deleted"


@dataclass(frozen=True)
class MemoryBankActivatedEvent(DomainEvent):
    """Emitted when a memory bank is activated."""

    bank_name: str
    timestamp: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now())

    @classmethod
    def of(cls, bank_name: str) -> Result["MemoryBankActivatedEvent"]:
        if not bank_name:
            return Result.ko([ErrorWithDetails("INVALID_MEMORY_BANK_ACTIVATED_EVENT", {
                "bank_name": bank_name,
            })])
        return Result.ok(cls(bank_name=bank_name))

    @property
    def event_type(self) -> str:
        return "memory_bank.activated"

    def get_name(self) -> str:
        return "memory_bank.activated"


@dataclass(frozen=True)
class MemoryBankSuspendedEvent(DomainEvent):
    """Emitted when a memory bank is suspended."""

    bank_name: str
    timestamp: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now())

    @classmethod
    def of(cls, bank_name: str) -> Result["MemoryBankSuspendedEvent"]:
        if not bank_name:
            return Result.ko([ErrorWithDetails("INVALID_MEMORY_BANK_SUSPENDED_EVENT", {
                "bank_name": bank_name,
            })])
        return Result.ok(cls(bank_name=bank_name))

    @property
    def event_type(self) -> str:
        return "memory_bank.suspended"

    def get_name(self) -> str:
        return "memory_bank.suspended"
