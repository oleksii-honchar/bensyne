"""Concrete domain events for memory bank operations.

Memory bank management is an infrastructure concern — these events
are emitted by the domain aggregate but consumed by infrastructure
to route storage operations.

Each event implements DomainEvent ABC and has a factory method of() that
returns Result, validating non-empty inputs.
"""

from dataclasses import dataclass
from datetime import datetime

from src.utils.result import DomainEvent, ErrorWithDetails, Result


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
